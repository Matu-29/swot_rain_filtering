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
    """Result of filtering one SWOT pass."""

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
    """Aggregated results for a batch run."""

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
    """Write a human-readable log of failures, warnings, and run summary."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    attempted = len(outcomes)
    written = sum(1 for o in outcomes if o.ok)
    skipped = sum(1 for o in outcomes if o.status == "skipped_existing")
    failed = [o for o in outcomes if o.failed]
    warned = [o for o in outcomes if o.status == "ok_with_warnings"]

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
    apply_fine_scale: bool = True,
    output_path: str | Path | None = None,
    overwrite: bool = False,
) -> FilterOutcome:
    """
    Apply IMERG bulldozer filter (and optional fine-scale filter) to one SWOT file.

    Returns a :class:`FilterOutcome` describing success or failure.
    """
    swot_path = Path(swot_path)
    imerg_kwargs = {}
    if imerg_root is not None:
        imerg_kwargs["imerg_root"] = Path(imerg_root)

    try:
        ds_swot = xr.open_dataset(swot_path)
    except Exception as exc:
        return FilterOutcome(swot_path, "swot_open_error", str(exc))

    try:
        ds_swot, t_start_str, t_end_str = st.quick_format_ds_swot(ds_swot)

        lon_min = float(np.nanmin(ds_swot.longitude.values))
        lon_max = float(np.nanmax(ds_swot.longitude.values))
        lat_min = float(np.nanmin(ds_swot.latitude.values))
        lat_max = float(np.nanmax(ds_swot.latitude.values))

        t_start = pd.to_datetime(t_start_str, format="%d/%m/%Y %H:%M:%S").tz_localize("UTC")
        t_end = pd.to_datetime(t_end_str, format="%d/%m/%Y %H:%M:%S").tz_localize("UTC")
        t_mid = t_start + (t_end - t_start) / 2

        f_c = rt.imerg_closest(t_mid, **imerg_kwargs)
        if f_c is None:
            reason = f"No IMERG file for t_mid={t_mid}"
            print(f"[WARN] {swot_path.name}: {reason}")
            return FilterOutcome(swot_path, "imerg_missing", reason)

        try:
            precip, lon_imerg, lat_imerg = rt.read_imerg_precip(
                f_c, lon_min, lon_max, lat_min, lat_max
            )
        except Exception as exc:
            reason = f"IMERG read {f_c.name}: {exc}"
            print(f"[WARN] {swot_path.name}: {reason}")
            return FilterOutcome(swot_path, "imerg_read_error", reason)

        da_imerg = xr.DataArray(
            precip, coords={"lat": lat_imerg, "lon": lon_imerg}, dims=["lat", "lon"]
        )
        da_regrid = da_imerg.interp(
            lat=ds_swot.latitude, lon=ds_swot.longitude, method="linear"
        )

        ds_swot["IMERG_rain_rate"] = (("num_lines", "num_pixels"), da_regrid.data)
        ds_swot["bulldozer_mask"] = (
            ("num_lines", "num_pixels"),
            (da_regrid.data > imerg_rain_threshold).astype(int),
        )

        fine_scale_warning = ""
        if apply_fine_scale:
            ds_bulldozered = ds_swot.where(ds_swot.bulldozer_mask == 0)
            try:
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
                )
                ds_swot["fine_scale_filter_mask"] = (
                    ("num_lines", "num_pixels"),
                    ds_fine.fine_scale_filter.data,
                )
            except (AttributeError, ValueError) as exc:
                fine_scale_warning = f"fine_scale_filter_failed: {exc}"
                print(f"[WARN] {swot_path.name}: {fine_scale_warning}")

        if output_path is not None:
            out = Path(output_path)
            if out.exists() and not overwrite and out.resolve() != swot_path.resolve():
                return FilterOutcome(
                    swot_path,
                    "output_exists",
                    f"Output exists (use --overwrite): {out}",
                    output_path=out,
                )
            out.parent.mkdir(parents=True, exist_ok=True)

            ds_out = ds_swot.load()
            ds_swot.close()
            ds_swot = None
            if out.resolve() == swot_path.resolve():
                tmp = out.with_name(out.name + ".tmp")
                ds_out.to_netcdf(tmp)
                tmp.replace(out)
            else:
                ds_out.to_netcdf(out)
            ds_out.close()

            status = "ok_with_warnings" if fine_scale_warning else "ok"
            return FilterOutcome(swot_path, status, fine_scale_warning, output_path=out)

        status = "ok_with_warnings" if fine_scale_warning else "ok"
        return FilterOutcome(swot_path, status, fine_scale_warning)
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
    if not inplace:
        if output_dir is None:
            raise ValueError("output_dir is required unless inplace=True")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    if failure_log is None and output_dir is not None and not inplace:
        failure_log = Path(output_dir) / "filter_failures.log"
    elif failure_log is not None:
        failure_log = Path(failure_log)

    result = FilterBatchResult()

    for swot_file in tqdm(swot_files, desc="SWOT rain filter"):
        swot_file = Path(swot_file)
        out = swot_file if inplace else Path(output_dir) / swot_file.name
        if skip_existing and not overwrite and out.exists():
            result.outcomes.append(
                FilterOutcome(swot_file, "skipped_existing", output_path=out)
            )
            continue

        outcome = filter_one_pass(
            swot_file,
            output_path=out,
            overwrite=overwrite or inplace,
            **filter_kwargs,
        )
        result.outcomes.append(outcome)
        if outcome.ok:
            result.written.append(out)

    skipped = result.skipped_existing
    if skipped:
        print(f"Skipped {len(skipped)} existing output(s)")

    if failure_log is not None:
        write_filter_run_log(result.outcomes, failure_log, discovered=discovered)

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
    swot_root = Path(swot_root)
    if not inplace:
        if output_dir is None:
            raise ValueError("output_dir is required unless inplace=True")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    all_files = sorted(swot_root.glob(pattern))
    if start_date is not None or end_date is not None:
        files = select_swot_files_by_date(
            all_files,
            start_date=start_date,
            end_date=end_date,
        )
        print(
            f"Date filter [{start_date or '...'} → {end_date or '...'}]: "
            f"{len(files)}/{len(all_files)} file(s) selected"
        )
    else:
        files = all_files

    discovered = len(files)
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
