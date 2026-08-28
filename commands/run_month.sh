#!/usr/bin/env bash
# Run rain filtering for one calendar month (CERSAT + gap mirror discovery).
#
# Usage:
#   bash commands/run_month.sh 2025 3
#   bash commands/run_month.sh 2025 03 --skip-existing
#
set -euo pipefail # exit on error
ROOT="$(cd "$(dirname "$0")/.." && pwd)" # root directory of the project

YEAR="${1:?Usage: run_month.sh YEAR MONTH [extra run_filter args...]}" # year to process
MONTH="${2:?Usage: run_month.sh YEAR MONTH [extra run_filter args...]}" # month to process
shift 2 # shift arguments

MONTH_PADDED="$(printf "%02d" "$MONTH")" # pad month with leading zeros
MONTH_TAG="${YEAR}_${MONTH_PADDED}" # month tag

# Gap mirror (Feb–Apr 2025 PGD0, etc.) — searched before CERSAT on name conflicts
SWOT_EXTRA_BASE="${SWOT_EXTRA_BASE:-/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT/2025/SWOT_L2_KARIN_LR_WindWave_AVISO}" # extra SWOT base
IMERG_ROOT="${IMERG_ROOT:-/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b}" # IMERG root
OUTPUT_BASE="${OUTPUT_BASE:-/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED}" # output base
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_BASE}/${YEAR}/${MONTH_PADDED}}"
FAILURE_LOG="${FAILURE_LOG:-${ROOT}/logs/monthly_${YEAR}/failures_${YEAR}_${MONTH_PADDED}.log}"

# Python env on compute nodes (PBS often has no conda in PATH)
CONDA_PREFIX="${CONDA_PREFIX:-/home1/datahome/ilarroch/conda-env/seastatesenv}" # conda environment
PYTHON="${PYTHON:-${CONDA_PREFIX}/bin/python}" # python executable
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}" # add conda library path

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: Python not found at $PYTHON" >&2 # print error message
  exit 1
fi
echo "Python: $($PYTHON --version 2>&1) ($PYTHON)" # print python version

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" # number of OpenMP threads
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" # number of OpenBLAS threads
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}" # number of MKL threads

START_TS="$(date -u +"%Y-%m-%d %H:%M:%S UTC")" # start time
echo "=== SWOT rain filter: ${YEAR}-${MONTH_PADDED} ==="
echo "Started: ${START_TS}" # print start time
echo "Output: ${OUTPUT_DIR}" # print output directory
echo "Failure log: ${FAILURE_LOG}"

"$PYTHON" "$ROOT/commands/run_filter.py" \
  --discover-karin \
  --month "${YEAR}-${MONTH_PADDED}" \
  --swot-extra-base "$SWOT_EXTRA_BASE" \
  --imerg-root "$IMERG_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --failure-log "$FAILURE_LOG" \
  --skip-existing \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0 \
  --window-size 60 \
  --kernel-size-nan 1 \
  --step-to-crop-at-edges 0 \
  --untrustable-hs 40.0 \
  "$@"

END_TS="$(date -u +"%Y-%m-%d %H:%M:%S UTC")" # end time
echo "Finished: ${END_TS}" # print end time
echo "Elapsed: ${SECONDS}s ($(printf '%02d:%02d:%02d' $((SECONDS/3600)) $((SECONDS%3600/60)) $((SECONDS%60))))" # print elapsed time
