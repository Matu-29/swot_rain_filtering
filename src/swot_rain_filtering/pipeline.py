"""End-to-end rain filtering for one SWOT pass or a directory of passes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from tqdm import tqdm

from . import rain_tools as rt
from . import swot_tools as st
from .io import select_swot_files_by_date


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
) -> xr.Dataset | None:
    """
    Apply IMERG bulldozer filter (and optional fine-scale filter) to one SWOT file.

    Returns the filtered dataset, or None if IMERG could not be matched/read.
    If ``output_path`` is set, writes NetCDF there (creates parent dirs).
    """
    swot_path = Path(swot_path)
    imerg_kwargs = {}
    if imerg_root is not None:
        imerg_kwargs["imerg_root"] = Path(imerg_root)

    ds_swot = xr.open_dataset(swot_path)
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
        print(f"[WARN] No IMERG file for {swot_path.name} (t_mid={t_mid})")
        ds_swot.close()
        return None

    try:
        precip, lon_imerg, lat_imerg = rt.read_imerg_precip(
            f_c, lon_min, lon_max, lat_min, lat_max
        )
    except Exception as exc:
        print(f"[WARN] IMERG read {f_c.name}: {exc}")
        ds_swot.close()
        return None

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
            print(f"[WARN] Fine-scale filter failed for {swot_path.name}: {exc}")

    if output_path is not None:
        out = Path(output_path)
        if out.exists() and not overwrite and out.resolve() != swot_path.resolve():
            raise FileExistsError(f"Output exists (use --overwrite): {out}")
        out.parent.mkdir(parents=True, exist_ok=True)

        # Load into memory and close the source handle before writing
        # (required for safe in-place overwrite of the same NetCDF).
        ds_out = ds_swot.load()
        ds_swot.close()
        if out.resolve() == swot_path.resolve():
            tmp = out.with_name(out.name + ".tmp")
            ds_out.to_netcdf(tmp)
            tmp.replace(out)
        else:
            ds_out.to_netcdf(out)
        return ds_out

    return ds_swot


def filter_directory(
    swot_root: str | Path,
    output_dir: str | Path | None = None,
    *,
    pattern: str = "*.nc",
    start_date: str | None = None,
    end_date: str | None = None,
    overwrite: bool = False,
    max_files: int | None = None,
    inplace: bool = False,
    **filter_kwargs: Any,
) -> list[Path]:
    """
    Run ``filter_one_pass`` on every NetCDF under ``swot_root``.

    Writes one file per input into ``output_dir`` (same basename), unless
    ``inplace=True`` (then each input file is overwritten).
    Optional ``start_date`` / ``end_date`` filter on pass start time (UTC).
    If ``max_files`` is set, only the first N sorted matches are processed.
    Returns the list of output paths successfully written.
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

    if max_files is not None:
        files = files[: max(0, max_files)]
    written: list[Path] = []

    for swot_file in tqdm(files, desc="SWOT rain filter"):
        out = swot_file if inplace else Path(output_dir) / swot_file.name
        ds = filter_one_pass(
            swot_file,
            output_path=out,
            overwrite=overwrite or inplace,
            **filter_kwargs,
        )
        if ds is not None:
            written.append(out)
            ds.close()

    return written
