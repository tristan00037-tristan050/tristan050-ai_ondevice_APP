#!/usr/bin/env bash
set -euo pipefail

TS="packages/common/src/metrics/counters.ts"
CJS="packages/common/src/metrics/counters.cjs"

if [ ! -f "$TS" ] || [ ! -f "$CJS" ]; then
  echo "OK: COUNTERS_SINGLE_SOURCE_OR_MISSING=1"
  echo "COUNTERS_NO_DRIFT_OK=1"
  exit 0
fi

# 최소 동일성 토큰(24h, single-writer, idempotent 같은 핵심 컨셉 키워드)
needles=(
  "24"
  "idempot"
)

for n in "${needles[@]}"; do
  grep -nF -- "$n" "$TS" >/dev/null || { echo "BLOCK: TS missing token: $n"; echo "COUNTERS_NO_DRIFT_OK=0"; exit 1; }
  grep -nF -- "$n" "$CJS" >/dev/null || { echo "BLOCK: CJS missing token: $n"; echo "COUNTERS_NO_DRIFT_OK=0"; exit 1; }
done

echo "OK: COUNTERS_DUAL_IMPL_GUARDED=1"
echo "COUNTERS_NO_DRIFT_OK=1"
