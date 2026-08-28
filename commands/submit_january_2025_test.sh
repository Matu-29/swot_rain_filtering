#!/usr/bin/env bash
# Submit a single PBS job for January 2025 (smoke / timing test).
#
# Usage:
#   bash commands/submit_january_2025_test.sh
#   DRY_RUN=1 bash commands/submit_january_2025_test.sh
#
# Optional — limit files for a quicker test:
#   MAX_FILES=3 bash commands/submit_january_2025_test.sh
#
# Run interactively on a compute node (no PBS):
#   bash commands/run_month.sh 2025 1
#   bash commands/run_month.sh 2025 1 --max-files 3
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

YEAR=2025
MONTH=1
WALLTIME="${WALLTIME:-08:00:00}"
MEM="${MEM:-8gb}"
NCPUS="${NCPUS:-1}"
QUEUE="${QUEUE:-}"
LOG_DIR="${LOG_DIR:-${ROOT}/logs/monthly_${YEAR}}"
JOB_NAME="swot_rain_${YEAR}_01_test"

mkdir -p "$LOG_DIR"
LOG_OUT="${LOG_DIR}/${JOB_NAME}.out"
LOG_ERR="${LOG_DIR}/${JOB_NAME}.err"

RUN_ARGS=( "$YEAR" "$MONTH" )
if [[ -n "${MAX_FILES:-}" ]]; then
  RUN_ARGS+=( --max-files "$MAX_FILES" )
fi
if [[ -n "${EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  RUN_ARGS+=( ${EXTRA_ARGS} )
fi

QSUB_ARGS=(
  -N "$JOB_NAME"
  -o "$LOG_OUT"
  -e "$LOG_ERR"
  -l "select=1:ncpus=${NCPUS}:mem=${MEM}"
  -l "walltime=${WALLTIME}"
)
if [[ -n "$QUEUE" ]]; then
  QSUB_ARGS+=(-q "$QUEUE")
fi

CMD=(qsub "${QSUB_ARGS[@]}" -- "$ROOT/commands/run_month.sh" "${RUN_ARGS[@]}")

echo "January 2025 test job"
echo "  logs:  ${LOG_OUT}"
echo "  output: ${OUTPUT_BASE:-/home/datawork-WW3/PROJECT/AMPHITRITE/SWOT_RAIN_FILTERED}/2025/01/"
echo "  command: ${CMD[*]}"

if [[ "${DRY_RUN:-0}" != "1" ]]; then
  JOB_ID=$("${CMD[@]}")
  echo "Submitted: ${JOB_ID}"
  echo "Monitor:   qstat ${JOB_ID}"
  echo "Tail log:  tail -f ${LOG_OUT}"
fi
