"""SWOT rain filtering: IMERG bulldozer + fine-scale Matu filter."""

from . import rain_tools, swot_tools
from .io import (
    month_date_bounds,
    parse_date_bound,
    parse_month_arg,
    parse_swot_filename_times,
    select_swot_files_by_date,
)
from .karin_paths import discover_karin_files_for_period
from .pipeline import (
    FilterBatchResult,
    FilterOutcome,
    filter_directory,
    filter_file_list,
    filter_one_pass,
    write_filter_run_log,
)

__all__ = [
    "rain_tools",
    "swot_tools",
    "parse_swot_filename_times",
    "parse_date_bound",
    "parse_month_arg",
    "month_date_bounds",
    "select_swot_files_by_date",
    "discover_karin_files_for_period",
    "FilterOutcome",
    "FilterBatchResult",
    "write_filter_run_log",
    "filter_one_pass",
    "filter_file_list",
    "filter_directory",
]
