#!/usr/bin/env bash
# Default rain-filtering parameters (IMERG bulldozer + Matu fine-scale)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SWOT_ROOT="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO/PGD0"
IMERG_ROOT="/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b"
OUTPUT_DIR="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED/"

# Avoid matplotlib error (Ines env)

# source "$(conda info --base)/etc/profile.d/conda.sh"
# conda activate seastatesenv
# export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"

SWOT_FILE="/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO/PGD0/SWOT_L2_LR_SSH_WindWave_030_203_20250324T123323_20250324T132451_PGD0_01.nc"


python "$ROOT/commands/run_filter.py" \
  --swot-file "$SWOT_FILE" \
  --imerg-root "$IMERG_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  --overwrite \
  "$@"

