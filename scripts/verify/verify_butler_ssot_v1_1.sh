#!/usr/bin/env bash
set -euo pipefail
DOC="docs/ops/SSOT_BUTLER_DEV_V1_1.md"
test -s "$DOC" || { echo "BLOCK: missing $DOC"; exit 1; }

grep -nF "최상위 불변 계약" "$DOC" >/dev/null || { echo "BLOCK: missing invariants section"; exit 1; }
grep -nF "통합 순서(고정)" "$DOC" >/dev/null || { echo "BLOCK: missing integration order section"; exit 1; }
grep -nF "외부 AI 호출 0" "$DOC" >/dev/null || { echo "BLOCK: missing external calls zero rule"; exit 1; }

echo "BUTLER_SSOT_V1_1_OK=1"
exit 0
