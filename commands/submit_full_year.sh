#!/usr/bin/env bash
# Submit one PBS job per month (default: all 12 months of 2025).
#
# Usage:
#   bash commands/submit_2025_months.sh
#   MONTHS="3 4 5" bash commands/submit_2025_months.sh
#   DRY_RUN=1 bash commands/submit_2025_months.sh   # print qsub commands only
#
set -euo pipefail # exit on error
ROOT="$(cd "$(dirname "$0")/.." && pwd)" # root directory of the project
YEAR="${YEAR:-2025}" # year to process
#MONTHS="${MONTHS:-2 3 4 5 6}" # months to process
MONTHS="${MONTHS:-7 8 9 10 11 12}"
WALLTIME="${WALLTIME:-04:00:00}" # walltime
MEM="${MEM:-8gb}" # memory
NCPUS="${NCPUS:-1}" # number of CPUs
QUEUE="${QUEUE:-}" # I leave it empty to use the default queue
LOG_DIR="${LOG_DIR:-${ROOT}/logs/monthly_${YEAR}}" # log directory

mkdir -p "$LOG_DIR" # create log directory if it doesn't exist

for m in $MONTHS; do
  MM="$(printf "%02d" "$m")"
  JOB_NAME="swot_rain_${YEAR}_${MM}" # job name
  LOG_OUT="${LOG_DIR}/${JOB_NAME}.out" # output log file
  LOG_ERR="${LOG_DIR}/${JOB_NAME}.err" # error log file

  QSUB_ARGS=(
    -N "$JOB_NAME" # job name
    -o "$LOG_OUT" # output log file
    -e "$LOG_ERR" # error log file
    -l "select=1:ncpus=${NCPUS}:mem=${MEM}" # number of CPUs and memory
    -l "walltime=${WALLTIME}" # walltime
  )
  if [[ -n "$QUEUE" ]]; then
    QSUB_ARGS+=(-q "$QUEUE") # queue
  fi

  CMD=(qsub "${QSUB_ARGS[@]}" -- "$ROOT/commands/run_month.sh" "$YEAR" "$m") # command to run

  echo "Submit ${YEAR}-${MM}: ${CMD[*]}" # print command to run
  if [[ "${DRY_RUN:-0}" != "1" ]]; then
    "${CMD[@]}" # run command
  fi
done
