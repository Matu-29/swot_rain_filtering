"""I/O helpers for SWOT / IMERG paths and filenames."""

from __future__ import annotations

import re
from datetime import datetime, timezone
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
