#!/usr/bin/env bash
# Default rain-filtering parameters (IMERG bulldozer + Matu fine-scale)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SWOT_ROOT="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO/PGD0"
IMERG_ROOT="/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b"

# Optional UTC date window (inclusive); leave empty to process all files
START_DATE=""
END_DATE=""

DATE_ARGS=()
if [[ -n "${START_DATE:-}" ]]; then
  DATE_ARGS+=(--start-date "$START_DATE")
fi
if [[ -n "${END_DATE:-}" ]]; then
  DATE_ARGS+=(--end-date "$END_DATE")
fi

python "$ROOT/commands/run_filter.py" \
  --swot-root "$SWOT_ROOT" \
  --imerg-root "$IMERG_ROOT" \
  --inplace \
  "${DATE_ARGS[@]}" \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  "$@"

