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

# guard
CONTRACTS_OUT="$(bash scripts/verify/verify_repo_contracts.sh 2>&1 || true)"

if echo "$CONTRACTS_OUT" | grep -q "WORKFLOW_LINT_SEALED_OK=1"; then
  echo "WORKFLOW_LINT_SEALED_OK=1" >> "$OUT"
else
  echo "WORKFLOW_LINT_SEALED_OK=0" >> "$OUT"
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
