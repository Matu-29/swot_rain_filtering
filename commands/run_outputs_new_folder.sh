#!/usr/bin/env bash
# Default rain-filtering parameters (IMERG bulldozer + Matu fine-scale)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SWOT_ROOT="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO/PGD0"
IMERG_ROOT="/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b"
OUTPUT_DIR="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED/"

# Write to a separate folder (safe default):
python "$ROOT/commands/run_filter.py" \
  --swot-root "$SWOT_ROOT" \
  --imerg-root "$IMERG_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  "$@"
