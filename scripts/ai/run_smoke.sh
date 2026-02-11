#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest
OUT="ai/reports/latest/summary.md"

START=$(date +%s)

echo "# AI Smoke Result" > "$OUT"
echo "- DATE: $(date -Iseconds)" >> "$OUT"
echo "- MODE: smoke" >> "$OUT"
echo "- RESULT: OK" >> "$OUT"
echo "- NOTE: placeholder runner (replace with real on-device inference later)" >> "$OUT"

END=$(date +%s)
echo "- ELAPSED_SEC: $((END-START))" >> "$OUT"

echo "OK: wrote $OUT"
