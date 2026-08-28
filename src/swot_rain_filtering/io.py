"""I/O helpers for SWOT / IMERG paths and filenames."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SWOT_FN_RE = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_")
_SWOT_FN_FMT = "%Y%m%dT%H%M%S"


def parse_swot_filename_times(fname: str | Path) -> tuple[datetime | None, datetime | None]:
    """Extract (t_start, t_end) from a SWOT filename, or (None, None)."""
    name = Path(fname).name
    m = _SWOT_FN_RE.search(name)
    if not m:
        return None, None
    t0 = datetime.strptime(m.group(1), _SWOT_FN_FMT).replace(tzinfo=timezone.utc)
    t1 = datetime.strptime(m.group(2), _SWOT_FN_FMT).replace(tzinfo=timezone.utc)
    return t0, t1


def parse_date_bound(
    value: str | datetime | None,
    *,
    as_end: bool = False,
) -> datetime | None:
    """
    Parse a CLI date bound into a timezone-aware UTC datetime.

    Accepted formats:
    - ``YYYY-MM-DD`` (whole calendar day; end bound uses 23:59:59 UTC)
    - ``YYYYMMDD``
    - ``YYYYMMDDTHHMMSS`` or ``YYYY-MM-DDTHH:MM:SS``
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    text = str(value).strip()
    if not text:
        return None

    date_only = False
    if re.fullmatch(r"\d{8}", text):
        dt = datetime.strptime(text, "%Y%m%d")
        date_only = True
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        dt = datetime.strptime(text, "%Y-%m-%d")
        date_only = True
    elif "T" in text:
        for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H%M%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unrecognized datetime format: {value!r}")
    else:
        raise ValueError(f"Unrecognized date format: {value!r}")

    if date_only and as_end:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)

    return dt.replace(tzinfo=timezone.utc)


def select_swot_files_by_date(
    files: list[Path] | Path,
    *,
    start_date: str | datetime | None = None,
    end_date: str | datetime | None = None,
    pattern: str = "*.nc",
    warn_unparseable: bool = True,
) -> list[Path]:
    """
    Keep SWOT NetCDF paths whose pass start time falls in ``[start_date, end_date]``.

    Pass times are read from the SWOT filename (``..._YYYYMMDDTHHMMSS_...``).
    Date-only bounds are inclusive on calendar days (UTC).

    Parameters
    ----------
    files
        List of file paths, or a directory that will be searched with ``pattern``.
    """
    if isinstance(files, Path):
        candidates = sorted(files.glob(pattern))
    else:
        candidates = sorted(Path(p) for p in files)

    start = parse_date_bound(start_date, as_end=False)
    end = parse_date_bound(end_date, as_end=True)

    if start is not None and end is not None and start > end:
        raise ValueError(f"start_date ({start}) must be <= end_date ({end})")

    selected: list[Path] = []
    for path in candidates:
        t_start, _ = parse_swot_filename_times(path)
        if t_start is None:
            if warn_unparseable:
                print(f"[WARN] Skipping file with unparseable SWOT times: {path.name}")
            continue
        if start is not None and t_start < start:
            continue
        if end is not None and t_start > end:
            continue
        selected.append(path)

    return selected
