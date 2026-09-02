"""End-to-end rain filtering for one SWOT pass or a directory of passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from tqdm import tqdm

from . import rain_tools as rt
from . import swot_tools as st
from .io import select_swot_files_by_date


@dataclass
class FilterOutcome:
    """Result of filtering one SWOT pass. Allows to know if the filtering was successful or not.

    :param swot_path: Path to the SWOT file.
    :param status: Status of the filtering.
    :param reason: Reason for the status.
    :param output_path: Path to the output file.

    """

    swot_path: Path
    status: str
    reason: str = ""
    output_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "ok_with_warnings")

    @property
    def failed(self) -> bool:
        return self.status not in ("ok", "ok_with_warnings", "skipped_existing")


@dataclass
class FilterBatchResult:
    """Aggregated results for a batch run. 
    A batch run is a run of the filtering on a list of SWOT files.
    :param written: List of paths to the output files. 
    :param outcomes: List of :class:`FilterOutcome` objects. (to know if the filtering was successful or not)
    """

    written: list[Path] = field(default_factory=list)
    outcomes: list[FilterOutcome] = field(default_factory=list)

    @property
    def failed(self) -> list[FilterOutcome]:
        return [o for o in self.outcomes if o.failed]

    @property
    def skipped_existing(self) -> list[FilterOutcome]:
        return [o for o in self.outcomes if o.status == "skipped_existing"]

    @property
    def warnings(self) -> list[FilterOutcome]:
        return [o for o in self.outcomes if o.status == "ok_with_warnings"]


def write_filter_run_log(
    outcomes: list[FilterOutcome],
    log_path: Path,
    *,
    discovered: int | None = None,
) -> None:
    """Write a log file of the filtering run.
    :param outcomes: List of :class:`FilterOutcome` objects. (to know if the filtering was successful or not)
    :param log_path: Path to the log file.
    :param discovered: Number of files discovered.
    """
    # Create the log file.
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Count the number of files attempted, written, skipped, failed, and warned.
    attempted = len(outcomes)
    written = sum(1 for o in outcomes if o.ok)
    skipped = sum(1 for o in outcomes if o.status == "skipped_existing")
    failed = [o for o in outcomes if o.failed]
    warned = [o for o in outcomes if o.status == "ok_with_warnings"]

    # Write the log file.
    lines = [
        f"# SWOT rain filter run log",
        f"# generated_utc: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if discovered is not None:
        lines.append(f"# discovered: {discovered}")
    lines.append(f"# attempted: {attempted}")
    lines.append(f"# written: {written}")
    lines.append(f"# skipped_existing: {skipped}")
    lines.append(f"# failed: {len(failed)}")
    lines.append(f"# ok_with_warnings: {len(warned)}")
    lines.append("")
    lines.append("# status\tswot_path\treason")

    for outcome in outcomes:
        if outcome.status in ("ok", "skipped_existing"):
            continue
        path = str(outcome.swot_path)
        reason = outcome.reason.replace("\t", " ").replace("\n", " ")
        lines.append(f"{outcome.status}\t{path}\t{reason}")

    if warned:
        lines.append("")
        lines.append("# Warnings (output written, but fine-scale filter failed):")
        for outcome in warned:
            path = str(outcome.swot_path)
            reason = outcome.reason.replace("\t", " ").replace("\n", " ")
            lines.append(f"ok_with_warnings\t{path}\t{reason}")

    log_path.write_text("\n".join(lines) + "\n")
    print(f"Run log: {log_path} ({len(failed)} failed, {len(warned)} warning(s))")


def filter_one_pass(
    swot_path: str | Path,
    *,
    imerg_root: str | Path | None = None,
    imerg_rain_threshold: float = 0.1,
    scale_MAD: float = 5.0,
    window_size: int = 60,
    kernel_size_nan: int = 1,
    step_to_crop_at_edges: int = 0,
    untrustable_hs: float = 40.0,
    native_filtering: bool = True,
    remove_rain: bool = False,
    already_flipped: bool = False,
    apply_fine_scale: bool = True,
    output_path: str | Path | None = None,
    overwrite: bool = False,
) -> FilterOutcome:
    """
    Apply IMERG bulldozer filter (and optional fine-scale filter) to one SWOT file.

    Returns a :class:`FilterOutcome` describing success or failure.
    """
    # Open the SWOT file.
    swot_path = Path(swot_path)
    imerg_kwargs = {}
    if imerg_root is not None:
        imerg_kwargs["imerg_root"] = Path(imerg_root)

    ds_swot = None
    try:
        ds_swot = xr.open_dataset(swot_path)
    except Exception as exc:
        return FilterOutcome(swot_path, "swot_open_error", str(exc))

    # Try to format the SWOT file.
    try:
        try:
            ds_swot, t_start_str, t_end_str = st.quick_format_ds_swot(ds_swot)     # Warning, by doing this, we must be aware that we must not redo 
            # ds_swot.coords["longitude"] = (ds_swot.coords["longitude"] + 180) % 360 - 180 by error with the function st.format_ds_swot.
            # therefore, we set the parameter already_flipped = True to prevent this from happening when performing the fine_scale_filter, using st.format_ds_swot.
            already_flipped = True
        except (AttributeError, TypeError, ValueError) as exc:
            reason = f"quick_format_ds_swot: {exc}"
            print(f"[WARN] {swot_path.name}: {reason}")
            return FilterOutcome(swot_path, "swot_format_error", reason)

        lon_min = float(np.nanmin(ds_swot.longitude.values))
        lon_max = float(np.nanmax(ds_swot.longitude.values))
        lat_min = float(np.nanmin(ds_swot.latitude.values))
        lat_max = float(np.nanmax(ds_swot.latitude.values))

        t_start = pd.to_datetime(t_start_str, format="%d/%m/%Y %H:%M:%S").tz_localize("UTC")
        t_end = pd.to_datetime(t_end_str, format="%d/%m/%Y %H:%M:%S").tz_localize("UTC")
        t_mid = t_start + (t_end - t_start) / 2

        # Find the closest IMERG file.
        f_c = rt.imerg_closest(t_mid, **imerg_kwargs)
        if f_c is None:
            reason = f"No IMERG file for t_mid={t_mid}"
            print(f"[WARN] {swot_path.name}: {reason}")
            return FilterOutcome(swot_path, "imerg_missing", reason)

        # Read the IMERG file.
        try:
            precip, lon_imerg, lat_imerg = rt.read_imerg_precip(f_c, lon_min, lon_max, lat_min, lat_max)
        
        # If an error occurs, record the failure and continue with the next file.
        except Exception as exc:
            reason = f"IMERG read {f_c.name}: {exc}"
            print(f"[WARN] {swot_path.name}: {reason}")
            return FilterOutcome(swot_path, "imerg_read_error", reason)

        # Regrid the IMERG data to the SWOT grid.
        da_imerg = xr.DataArray(precip, coords={"lat": lat_imerg, "lon": lon_imerg}, dims=["lat", "lon"])
        da_regrid = da_imerg.interp(lat=ds_swot.latitude, lon=ds_swot.longitude, method="linear")

        # Create the bulldozer mask.
        ds_swot["IMERG_rain_rate"] = (("num_lines", "num_pixels"), da_regrid.data)
        ds_swot["bulldozer_mask"] = (("num_lines", "num_pixels"), (da_regrid.data > imerg_rain_threshold).astype(int))

        # Create the fine-scale filter mask.
        fine_scale_warning = ""
        if apply_fine_scale:
            ds_bulldozered = ds_swot.where(ds_swot.bulldozer_mask == 0)
            try:
                # ATTENTION, le fait de faire ça provoque un double changement des coordonnées en longitude.
                # Ajout du paramètre "already_flipped=True", pour spécifier que la ligne
                # ds_swot.coords["longitude"] = (ds_swot.coords["longitude"] + 180) % 360 - 180
                # de la fonction quick_format_ds_swot a déjà eu lieu

                # Format the SWOT file for the fine-scale filter.
                ds_fine, _, _ = st.format_ds_swot(
                    ds_bulldozered,
                    lon_min,
                    lon_max,
                    lat_min,
                    lat_max,
                    scale_MAD=scale_MAD,
                    untrustable_hs=untrustable_hs,
                    kernel_size_nan=kernel_size_nan,
                    step_to_crop_at_edges=step_to_crop_at_edges,
                    remove_rain=remove_rain,
                    window_size=window_size,
                    native_filtering=native_filtering,
                    already_flipped=already_flipped
                )
                # Create the fine-scale filter mask.
                ds_swot["fine_scale_filter_mask"] = (("num_lines", "num_pixels"), ds_fine.fine_scale_filter.data)
            # If an error occurs, record the failure and continue with the next file.
            except (AttributeError, ValueError) as exc:
                fine_scale_warning = f"fine_scale_filter_failed: {exc}"
                print(f"[WARN] {swot_path.name}: {fine_scale_warning}")

        # Write the output file.
        if output_path is not None:
            # Check if the output file already exists.
            out = Path(output_path)
            if out.exists() and not overwrite and out.resolve() != swot_path.resolve():
                return FilterOutcome(swot_path, "output_exists", f"Output exists (use --overwrite): {out}", output_path=out)
            out.parent.mkdir(parents=True, exist_ok=True)

            # Load the SWOT file.
            ds_out = ds_swot.load()
            ds_swot.close()
            ds_swot = None
            try:
                if out.resolve() == swot_path.resolve():
                    tmp = out.with_name(out.name + ".tmp")
                    ds_out.to_netcdf(tmp)
                    tmp.replace(out)
                else:
                    ds_out.to_netcdf(out)
            except Exception as exc:
                ds_out.close()
                reason = f"write_error: {exc}"
                print(f"[WARN] {swot_path.name}: {reason}")
                return FilterOutcome(swot_path, "write_error", reason, output_path=out)
            ds_out.close()

            status = "ok_with_warnings" if fine_scale_warning else "ok"
            return FilterOutcome(swot_path, status, fine_scale_warning, output_path=out)

        status = "ok_with_warnings" if fine_scale_warning else "ok"
        return FilterOutcome(swot_path, status, fine_scale_warning)
    except Exception as exc:
        reason = str(exc)
        print(f"[WARN] {swot_path.name}: {reason}")
        return FilterOutcome(swot_path, "filter_error", reason)
    finally:
        if ds_swot is not None:
            ds_swot.close()


def filter_file_list(
    swot_files: list[Path],
    output_dir: str | Path | None = None,
    *,
    overwrite: bool = False,
    skip_existing: bool = False,
    inplace: bool = False,
    failure_log: str | Path | None = None,
    discovered: int | None = None,
    **filter_kwargs: Any,
) -> FilterBatchResult:
    """
    Run ``filter_one_pass`` on an explicit list of SWOT NetCDF paths.

    When ``skip_existing=True``, skip outputs that already exist (unless
    ``overwrite`` is set). Failures are recorded in ``failure_log``.
    """
    # Create the output directory to store the filtered files,
    # if we do not overwrite the input files.
    if not inplace:
        if output_dir is None:
            raise ValueError("output_dir is required unless inplace=True")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Keep track of the failure cases in a log file.
    if failure_log is None and output_dir is not None and not inplace:
        failure_log = Path(output_dir) / "filter_failures.log"
    elif failure_log is not None:
        failure_log = Path(failure_log)

    result = FilterBatchResult()

    # Process each SWOT file in the list.
    for swot_file in tqdm(swot_files, desc="SWOT rain filter"):
        swot_file = Path(swot_file)
        out = swot_file if inplace else Path(output_dir) / swot_file.name

        # If the output file already exists
        # skip it unless we are overwriting.
        if skip_existing and not overwrite and out.exists():
            result.outcomes.append(FilterOutcome(swot_file, "skipped_existing", output_path=out))
            continue

        # Try to filter the SWOT file.
        try:
            outcome = filter_one_pass(swot_file, output_path=out, overwrite=overwrite or inplace, **filter_kwargs)

        # If an error occurs, record the failure 
        # and continue with the next file.
        except Exception as exc:
            reason = str(exc)
            print(f"[WARN] {swot_file.name}: unexpected error: {reason}")
            outcome = FilterOutcome(swot_file, "filter_error", reason)
        result.outcomes.append(outcome)
        if outcome.ok:
            result.written.append(out)

    skipped = result.skipped_existing
    if skipped:
        print(f"Skipped {len(skipped)} existing output(s)")

    # Sav the log of failures.
    if failure_log is not None:
        write_filter_run_log(result.outcomes, failure_log, discovered=discovered)

    # Print the number of failed files.
    failed = result.failed
    if failed:
        print(f"Failed {len(failed)} file(s) — see {failure_log}")

    return result


def filter_directory(
    swot_root: str | Path,
    output_dir: str | Path | None = None,
    *,
    pattern: str = "*.nc",
    start_date: str | None = None,
    end_date: str | None = None,
    overwrite: bool = False,
    skip_existing: bool = False,
    max_files: int | None = None,
    inplace: bool = False,
    failure_log: str | Path | None = None,
    **filter_kwargs: Any,
) -> FilterBatchResult:
    """
    Run ``filter_one_pass`` on every NetCDF under ``swot_root``.

    Writes one file per input into ``output_dir`` (same basename), unless
    ``inplace=True`` (then each input file is overwritten).
    Optional ``start_date`` / ``end_date`` filter on pass start time (UTC).
    If ``max_files`` is set, only the first N sorted matches are processed.
    """
    # Create the output directory to store the filtered files,
    # if we do not overwrite the input files.
    swot_root = Path(swot_root)
    if not inplace:
        if output_dir is None:
            raise ValueError("output_dir is required unless inplace=True")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Get the list of SWOT files to process.
    all_files = sorted(swot_root.glob(pattern))

    # Apply the date filter if provided 
    # (only select files within the date range)
    if start_date is not None or end_date is not None:
        files = select_swot_files_by_date(all_files, start_date=start_date, end_date=end_date)
        print(
            f"Date filter [{start_date or '...'} → {end_date or '...'}]: "
            f"{len(files)}/{len(all_files)} file(s) selected"
        )
    else:
        files = all_files

    # Keep track of the number of files discovered.
    discovered = len(files)

    # If max_files is set, only process the first N files.
    # (Useful for testing or debugging.)
    if max_files is not None:
        files = files[: max(0, max_files)]

    return filter_file_list(
        files,
        output_dir,
        overwrite=overwrite,
        skip_existing=skip_existing,
        inplace=inplace,
        failure_log=failure_log,
        discovered=discovered,
        **filter_kwargs,
    )
