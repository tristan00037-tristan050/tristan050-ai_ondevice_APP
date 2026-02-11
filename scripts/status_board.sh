#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs/status
OUT="docs/status/STATUS.txt"

echo "STATUS_SNAPSHOT" > "$OUT"
echo "DATE=$(date -Iseconds)" >> "$OUT"
echo "GIT_SHA=$(git rev-parse HEAD)" >> "$OUT"

# evidence file
if [ -f docs/EXEC_TEAM3_REPORTS/2026-02-11.md ]; then
  echo "EVIDENCE_FILE_OK=1" >> "$OUT"
else
  echo "EVIDENCE_FILE_OK=0" >> "$OUT"
fi

# workflow-lint seal status (independent; no false negative from other guards)
FILE=".github/workflows/workflow-lint.yml"

# fail-closed: file missing/unreadable => 0
if [ ! -r "$FILE" ]; then
  echo "WORKFLOW_LINT_SEALED_OK=0" >> "$OUT"
else
  WRITE_RE='["'"'"']?[Ww][Rr][Ii][Tt][Ee]["'"'"']?'

  # Any write-all is forbidden
  if grep -Eq "^[[:space:]]*permissions[[:space:]]*:[[:space:]]*$WRITE_RE-all[[:space:]]*$" "$FILE"; then
    echo "WORKFLOW_LINT_SEALED_OK=0" >> "$OUT"

  # Forbidden keys with write (YAML-safe: quotes/spacing variants)
  elif grep -Eq "^[[:space:]]*(id-token|attestations|artifact-metadata)[[:space:]]*:[[:space:]]*$WRITE_RE([[:space:]]*#.*)?$" "$FILE"; then
    echo "WORKFLOW_LINT_SEALED_OK=0" >> "$OUT"

  # attest-build-provenance must not appear
  elif grep -Eq "attest-build-provenance" "$FILE"; then
    echo "WORKFLOW_LINT_SEALED_OK=0" >> "$OUT"

  else
    echo "WORKFLOW_LINT_SEALED_OK=1" >> "$OUT"
  fi
fi

# ai report presence
if [ -f ai/reports/latest/metrics.json ]; then
  echo "AI_METRICS_OK=1" >> "$OUT"
else
  echo "AI_METRICS_OK=0" >> "$OUT"
fi

if [ -f ai/reports/latest/summary.md ]; then
  echo "AI_SUMMARY_OK=1" >> "$OUT"
else
  echo "AI_SUMMARY_OK=0" >> "$OUT"
fi

echo "WROTE=$OUT"
cat "$OUT"
