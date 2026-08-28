"""SWOT KaRIn WindWave filesystem roots (CERSAT archive + optional gap mirror)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_KARIN_BASE = Path(
    "/home/datawork-cersat-public/project/mpc-sentinel1/data/ancillary/"
    "SWOT_L2_KARIN_LR_WindWave_AVISO"
)

KARIN_GLOB = "SWOT_L2_LR_SSH_WindWave_*_{day}T*.nc"


def _split_paths(value: str) -> list[Path]:
    return [Path(p.strip()) for p in value.split(",") if p.strip()]


# This is to find SWOT KARIN files in datarmor
# The default one is DEFAULT_KARIN_BASE
# The extra one is a folder where I downloaded missing Karin files in 2025 (Inès)

def parse_karin_bases(
    extra_base: str | Path | None = None,
    bases_override: str | None = None,
    *,
    extra_first: bool = False,
) -> list[Path]:
    """
    Return ordered KaRIn product base directories (each contains PID0/, PGD0/, …).

    When ``extra_first=True``, the gap mirror (``extra_base``) is searched before
    the default CERSAT base so local copies win on filename conflicts.
    """
    env_bases = os.environ.get("SWOT_KARIN_BASES")
    env_extra = os.environ.get("SWOT_KARIN_EXTRA_BASE")

    if bases_override:
        return _split_paths(str(bases_override))
    if env_bases:
        return _split_paths(env_bases)

    bases = [DEFAULT_KARIN_BASE]
    extra = extra_base or env_extra
    if extra:
        extra_path = Path(extra)
        if extra_first and extra_path not in bases:
            bases = [extra_path] + bases
        elif extra_path not in bases:
            bases.append(extra_path)
    return bases


def karin_version_order(query_time: datetime) -> list[str]:
    """PID0 from 2025-05-06 onward; PGD0 preferred before that."""
    if (query_time.year, query_time.month, query_time.day) >= (2025, 5, 6):
        return ["PID0", "PGD0"]
    return ["PGD0", "PID0"]


def karin_roots_for_time(
    query_time: datetime,
    *,
    extra_base: str | Path | None = None,
    bases_override: str | None = None,
    extra_first: bool = False,
) -> list[Path]:
    """Resolve versioned subdirs to search for one UTC day."""
    bases = parse_karin_bases(
        extra_base=extra_base,
        bases_override=bases_override,
        extra_first=extra_first,
    )
    versions = karin_version_order(query_time)
    roots: list[Path] = []
    for base in bases:
        for version in versions:
            roots.append(base / version)
    return roots


def list_karin_files_for_day(day_str: str, roots: list[Path]) -> list[Path]:
    """Glob WindWave granules for one UTC day across roots; dedupe by filename."""
    files: list[Path] = []
    seen: set[str] = set()
    pattern = KARIN_GLOB.format(day=day_str)
    for root in roots:
        if not root.is_dir():
            continue
        for fp in sorted(root.glob(pattern)):
            if fp.name in seen: # avoid duplicates
                continue
            seen.add(fp.name)
            files.append(fp)
    return files


def discover_karin_files_for_period(
    start_date: str,
    end_date: str,
    *,
    extra_base: str | Path | None = None,
    bases_override: str | None = None,
    extra_first: bool = True,
) -> list[Path]:
    """
    Collect KaRIn WindWave granules between ``start_date`` and ``end_date`` (UTC).

    Iterates day-by-day, applies PID0/PGD0 version order per day, and dedupes
    by filename (first root in search order wins).
    """
    from .io import parse_date_bound, select_swot_files_by_date

    start = parse_date_bound(start_date, as_end=False)
    end = parse_date_bound(end_date, as_end=True)
    if start is None or end is None:
        raise ValueError("start_date and end_date are required for discovery")

    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_day = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)

    collected: list[Path] = []
    seen: set[str] = set()
    while day <= end_day:
        day_str = day.strftime("%Y%m%d")
        roots = karin_roots_for_time(
            day,
            extra_base=extra_base,
            bases_override=bases_override,
            extra_first=extra_first,
        )
        for fp in list_karin_files_for_day(day_str, roots):
            if fp.name in seen:
                continue
            seen.add(fp.name)
            collected.append(fp)
        day += timedelta(days=1)

    return select_swot_files_by_date(
        collected,
        start_date=start_date,
        end_date=end_date,
        warn_unparseable=True,
    )
