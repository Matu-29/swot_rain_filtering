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

from swot_rain_filtering.io import parse_month_arg  # noqa: E402
from swot_rain_filtering.karin_paths import discover_karin_files_for_period  # noqa: E402
from swot_rain_filtering.pipeline import filter_directory, filter_file_list, filter_one_pass  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Apply IMERG bulldozer + Matu fine-scale rain filter to SWOT L2 files."
    )
    p.add_argument(
        "--swot-root",
        type=Path,
        help="Directory of SWOT NetCDF files (single-root mode)",
    )
    p.add_argument(
        "--swot-file",
        type=Path,
        help="Single SWOT NetCDF (overrides directory / discover mode)",
    )
    p.add_argument(
        "--discover-karin",
        action="store_true",
        help="Find files across CERSAT + gap mirror using KaRIn path rules",
    )
    p.add_argument(
        "--swot-extra-base",
        type=Path,
        default=None,
        help="Gap mirror base (…/SWOT_L2_KARIN_LR_WindWave_AVISO); searched before CERSAT",
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
    p.add_argument(
        "--month",
        default=None,
        metavar="YYYY-MM",
        help="Shorthand for one calendar month (sets start/end dates, UTC)",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files whose output NetCDF already exists",
    )
    p.add_argument(
        "--failure-log",
        type=Path,
        default=None,
        help="Log file for failures/warnings (default: OUTPUT_DIR/filter_failures.log)",
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

    start_date = args.start_date
    end_date = args.end_date
    if args.month:
        _, _, start_date, end_date = parse_month_arg(args.month)
        print(f"Month {args.month} → {start_date} … {end_date} (UTC)")

    if args.swot_file is None and args.swot_root is None and not args.discover_karin:
        print("Provide --swot-root, --discover-karin, or --swot-file.", file=sys.stderr)
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
        failure_log = args.failure_log
        if failure_log is None and not args.inplace:
            failure_log = args.output_dir / "filter_failures.log"
        outcome = filter_one_pass(
            args.swot_file,
            output_path=out,
            overwrite=args.overwrite or args.inplace,
            **filter_kwargs,
        )
        if failure_log is not None:
            from swot_rain_filtering.pipeline import write_filter_run_log  # noqa: E402

            write_filter_run_log([outcome], failure_log, discovered=1)
        if not outcome.ok:
            print(f"Failed: {args.swot_file} ({outcome.status}: {outcome.reason})")
            return 1
        print(f"Wrote {out}")
        if outcome.status == "ok_with_warnings":
            print(f"Warning: {outcome.reason}")
        return 0

    batch_kwargs = dict(
        overwrite=args.overwrite,
        skip_existing=args.skip_existing,
        inplace=args.inplace,
        failure_log=args.failure_log,
        **filter_kwargs,
    )

    if args.discover_karin:
        if not start_date or not end_date:
            print("--discover-karin requires --start-date/--end-date or --month.", file=sys.stderr)
            return 2
        files = discover_karin_files_for_period(
            start_date,
            end_date,
            extra_base=args.swot_extra_base,
            extra_first=True,
        )
        n_discovered = len(files)
        print(f"Discovered {n_discovered} KaRIn file(s) for {start_date} … {end_date}")
        if args.max_files is not None:
            files = files[: max(0, args.max_files)]
        batch = filter_file_list(
            files,
            args.output_dir,
            discovered=n_discovered,
            **batch_kwargs,
        )
    else:
        batch = filter_directory(
            args.swot_root,
            args.output_dir,
            pattern=args.pattern,
            start_date=start_date,
            end_date=end_date,
            max_files=args.max_files,
            **batch_kwargs,
        )

    dest = "inplace (overwrote inputs)" if args.inplace else str(args.output_dir)
    print(
        f"Done: {len(batch.written)} written, "
        f"{len(batch.failed)} failed, "
        f"{len(batch.skipped_existing)} skipped → {dest}"
    )
    return 1 if batch.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
