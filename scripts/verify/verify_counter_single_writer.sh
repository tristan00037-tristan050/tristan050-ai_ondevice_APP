#!/usr/bin/env bash
set -euo pipefail

COUNTER_SINGLE_WRITER_OK=0
cleanup(){ echo "COUNTER_SINGLE_WRITER_OK=${COUNTER_SINGLE_WRITER_OK}"; }
trap cleanup EXIT

# 금지: ops_counters/직접 증가/임의 저장 (rg 없으면 grep+find 폴백)
DIR="webcore_appcore_starter_4_17/backend/model_registry"
if command -v rg >/dev/null 2>&1; then
  BAD="$(rg -n --no-messages \
    -e 'incCounter\(' \
    -e 'LOCK_TIMEOUT_COUNT_24H' \
    -e 'PERSIST_CORRUPTED_COUNT_24H' \
    --glob '!**/ops_counters.ts' \
    "$DIR" 2>/dev/null || true)"
else
  BAD="$(find "$DIR" -type f \( -name '*.ts' -o -name '*.js' \) ! -path '*dist*' ! -path '*ops_counters.ts' -exec grep -nE 'incCounter\(|LOCK_TIMEOUT_COUNT_24H|PERSIST_CORRUPTED_COUNT_24H' {} + 2>/dev/null || true)"
fi

# 허용: packages/common/src/metrics/counters.ts 내부만
if [[ -n "$BAD" ]]; then
  echo "FAIL: counter direct bump patterns found (must use packages/common/src/metrics/counters.ts bump())"
  echo "$BAD"
  exit 1
fi

COUNTER_SINGLE_WRITER_OK=1
exit 0

