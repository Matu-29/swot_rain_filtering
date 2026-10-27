#!/usr/bin/env bash
# Quick test of the rain filter on a few SWOT L3 WindWave passes (swh2d group).

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PYTHON="/home/ilarroch/conda-env/seastatesenv/bin/python"
SWOT_ROOT="/scale/project/wave/WW3/PROJECT/SWOT/WindWave-L3"
IMERG_ROOT="/reference/remote-sensing/public/precipitation/precipitation-rate/global/nasa/multisensor/gpm_3imerghhl/v7b"

# IMERG_ROOT="/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b"
OUTPUT_DIR="/scale/project/wave/WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED/L3_test"

# Only standard L3 files (the [0-9] excludes the "Extended" files)
PATTERN="cycle_*/SWOT_L3_LR_WIND_WAVE_[0-9]*.nc"

# L3 is already quality-filtered upstream: no swh_karin_qual → --no-native-filtering
"$PYTHON" "$ROOT/commands/run_filter.py" \
  --l3 \
  --compress \
  --no-native-filtering \
  --swot-root "$SWOT_ROOT" \
  --pattern "$PATTERN" \
  --imerg-root "$IMERG_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --failure-log "$OUTPUT_DIR/filter_failures.log" \
  --skip-existing \
  --max-files 500 \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  --start-date 2024-12-04 \
  --end-date 2024-12-19 \
  "$@"
