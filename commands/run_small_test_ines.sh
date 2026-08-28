#!/usr/bin/env bash
# Default rain-filtering parameters (IMERG bulldozer + Matu fine-scale)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SWOT_ROOT="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO/PGD0"
IMERG_ROOT="/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b"
OUTPUT_DIR="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED/"

# Optional UTC date window (inclusive); leave empty to process all files
START_DATE="2025-03-24"
END_DATE="2025-03-24"

# Avoid matplotlib error (Ines env)

# source "$(conda info --base)/etc/profile.d/conda.sh"
# conda activate seastatesenv
# export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"

# Launch the filtering pipeline
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
  --output-dir "$OUTPUT_DIR" \
  "${DATE_ARGS[@]}" \
  --max-files 5 \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  "$@"

