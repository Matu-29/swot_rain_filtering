#!/usr/bin/env python3
"""CLI for SWOT rain filtering. Parameters are usually set in the bash launchers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without install: add ../src to path
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from swot_rain_filtering.pipeline import filter_directory, filter_one_pass  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Apply IMERG bulldozer + Matu fine-scale rain filter to SWOT L2 files."
    )
    p.add_argument(
        "--swot-root",
        type=Path,
        help="Directory of SWOT NetCDF files",
    )
    p.add_argument(
        "--swot-file",
        type=Path,
        help="Single SWOT NetCDF (overrides directory mode)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for filtered NetCDF outputs (not needed with --inplace)",
    )
    p.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite each input NetCDF with the filtered result",
    )
    p.add_argument(
        "--imerg-root",
        type=Path,
        default=None,
        help="IMERG archive root (default: path baked into rain_tools)",
    )
    p.add_argument("--pattern", default="*.nc", help="Glob under swot-root")
    p.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Process at most N files (sorted), useful for quick tests",
    )
    p.add_argument(
        "--start-date",
        default=None,
        help="Keep passes with start time on/after this date (YYYY-MM-DD or YYYYMMDD, UTC)",
    )
    p.add_argument(
        "--end-date",
        default=None,
        help="Keep passes with start time on/before this date (YYYY-MM-DD or YYYYMMDD, UTC)",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    p.add_argument(
        "--no-fine-scale",
        action="store_true",
        help="Skip Matu fine-scale filter (bulldozer only)",
    )
    p.add_argument(
        "--imerg-rain-threshold",
        type=float,
        default=0.1,
        help="Bulldozer threshold in mm/h",
    )
    p.add_argument("--scale-MAD", type=float, default=5.0, dest="scale_MAD")
    p.add_argument("--window-size", type=int, default=60)
    p.add_argument("--kernel-size-nan", type=int, default=1)
    p.add_argument("--step-to-crop-at-edges", type=int, default=0)
    p.add_argument("--untrustable-hs", type=float, default=40.0)
    p.add_argument(
        "--no-native-filtering",
        action="store_true",
        help="Do not restrict to swh_karin_qual == 0",
    )
    p.add_argument(
        "--remove-rain",
        action="store_true",
        help="Also apply SWOT rain_flag == 0",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.swot_file is None and args.swot_root is None:
        print("Provide --swot-root or --swot-file.", file=sys.stderr)
        return 2
    if not args.inplace and args.output_dir is None:
        print("Provide --output-dir, or use --inplace to overwrite inputs.", file=sys.stderr)
        return 2

    filter_kwargs = {
        "imerg_root": args.imerg_root,
        "imerg_rain_threshold": args.imerg_rain_threshold,
        "scale_MAD": args.scale_MAD,
        "window_size": args.window_size,
        "kernel_size_nan": args.kernel_size_nan,
        "step_to_crop_at_edges": args.step_to_crop_at_edges,
        "untrustable_hs": args.untrustable_hs,
        "native_filtering": not args.no_native_filtering,
        "remove_rain": args.remove_rain,
        "apply_fine_scale": not args.no_fine_scale,
    }
    if filter_kwargs["imerg_root"] is None:
        del filter_kwargs["imerg_root"]

    if args.swot_file is not None:
        out = args.swot_file if args.inplace else args.output_dir / args.swot_file.name
        if not args.inplace:
            args.output_dir.mkdir(parents=True, exist_ok=True)
        ds = filter_one_pass(
            args.swot_file,
            output_path=out,
            overwrite=args.overwrite or args.inplace,
            **filter_kwargs,
        )
        if ds is None:
            print(f"Failed: {args.swot_file}")
            return 1
        ds.close()
        print(f"Wrote {out}")
        return 0

    written = filter_directory(
        args.swot_root,
        args.output_dir,
        pattern=args.pattern,
        start_date=args.start_date,
        end_date=args.end_date,
        overwrite=args.overwrite,
        max_files=args.max_files,
        inplace=args.inplace,
        **filter_kwargs,
    )
    dest = "inplace (overwrote inputs)" if args.inplace else str(args.output_dir)
    print(f"Done: {len(written)} file(s) → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
