#!/usr/bin/env bash
# Verify exec mode v1: fail-closed on missing result, line count mismatch, or schema error.
set -euo pipefail

INPUTS=""
OUTDIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inputs)  INPUTS="$2";  shift 2 ;;
    --outdir)  OUTDIR="$2";  shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$INPUTS" || -z "$OUTDIR" ]]; then
  echo "Usage: $0 --inputs <path.jsonl> --outdir <dir>" >&2
  exit 1
fi

RESULT_FILE="${OUTDIR}/result.jsonl"
EXEC_MODE_V1_OK=0

if [[ ! -f "$RESULT_FILE" ]]; then
  echo "FAIL: result file missing: ${RESULT_FILE}" >&2
  echo "EXEC_MODE_V1_OK=0"
  exit 1
fi

INPUT_COUNT=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  ((INPUT_COUNT+=1)) || true
done < "$INPUTS"

RESULT_COUNT=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  ((RESULT_COUNT+=1)) || true
  # Schema: must have "id" and "result" (and valid JSON)
  if ! echo "$line" | grep -qE '"id"[[:space:]]*:' || ! echo "$line" | grep -qE '"result"[[:space:]]*:'; then
    echo "FAIL: result line missing required id/result: ${line}" >&2
    echo "EXEC_MODE_V1_OK=0"
    exit 1
  fi
done < "$RESULT_FILE"

if [[ $RESULT_COUNT -lt $INPUT_COUNT ]]; then
  echo "FAIL: result count ${RESULT_COUNT} < input count ${INPUT_COUNT}" >&2
  echo "EXEC_MODE_V1_OK=0"
  exit 1
fi

EXEC_MODE_V1_OK=1
echo "EXEC_MODE_V1_OK=1"
exit 0
