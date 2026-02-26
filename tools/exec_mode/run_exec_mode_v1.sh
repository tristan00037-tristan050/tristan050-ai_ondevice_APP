#!/usr/bin/env bash
# Run exec mode v1: read prompts, run engine (mock only in P2), write result.jsonl and update report.
set -euo pipefail

ENGINE=""
INPUTS=""
OUTDIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine)  ENGINE="$2";  shift 2 ;;
    --inputs)  INPUTS="$2";  shift 2 ;;
    --outdir)  OUTDIR="$2";  shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ENGINE" || -z "$INPUTS" || -z "$OUTDIR" ]]; then
  echo "Usage: $0 --engine <mock> --inputs <path.jsonl> --outdir <dir>" >&2
  exit 1
fi

if [[ "$ENGINE" != "mock" ]]; then
  echo "P2: only --engine mock is supported." >&2
  exit 1
fi

if [[ ! -f "$INPUTS" ]]; then
  echo "Inputs file not found: $INPUTS" >&2
  exit 1
fi

mkdir -p "$OUTDIR"
RESULT_FILE="${OUTDIR}/result.jsonl"
: > "$RESULT_FILE"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  id=$(echo "$line" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  prompt=$(echo "$line" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  if [[ -z "$id" ]]; then id="unknown"; fi
  if [[ -z "$prompt" ]]; then prompt=""; fi
  ts_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  result="[mock] OK"
  printf '%s\n' "{\"id\":\"${id}\",\"prompt\":\"${prompt}\",\"result\":\"${result}\",\"engine\":\"mock\",\"ts_utc\":\"${ts_utc}\"}" >> "$RESULT_FILE"
done < "$INPUTS"

# Update report (repo-root: tools/exec_mode -> repo root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPORT_MD="${REPO_ROOT}/docs/EXEC_MODE_REPORT_V1.md"
RUN_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COUNT=$(wc -l < "$RESULT_FILE" | tr -d ' ')
cat > "$REPORT_MD" << EOF
# Exec Mode V1 Report

**Last run:** ${RUN_TS}  
**Engine:** mock  
**Inputs:** \`${INPUTS}\`  
**Outdir:** \`${OUTDIR}\`  
**Result file:** \`${RESULT_FILE}\`  
**Result count:** ${COUNT}

## Latest result (preview)

\`\`\`jsonl
$(head -n 3 "$RESULT_FILE" 2>/dev/null || true)
\`\`\`

*This file is updated by \`tools/exec_mode/run_exec_mode_v1.sh\`.*
EOF

echo "run_exec_mode_v1: wrote ${RESULT_FILE} (${COUNT} rows), updated ${REPORT_MD}"
