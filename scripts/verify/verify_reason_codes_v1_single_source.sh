#!/usr/bin/env bash
set -euo pipefail

REASON_CODE_SINGLE_SOURCE_OK=0
REASON_CODE_DRIFT_GUARD_OK=0

cleanup() {
  echo "REASON_CODE_SINGLE_SOURCE_OK=${REASON_CODE_SINGLE_SOURCE_OK}"
  echo "REASON_CODE_DRIFT_GUARD_OK=${REASON_CODE_DRIFT_GUARD_OK}"
}
trap cleanup EXIT

ENUM="packages/common/src/reason_codes/reason_codes_v1.ts"
test -f "$ENUM" || { echo "BLOCK: missing $ENUM"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

# 프로덕션 코드만 대상으로 리터럴 금지(오탐 최소화)
if have_rg; then
  HITS="$(rg -n \
    --glob 'packages/**/src/**/*.ts' \
    --glob '!packages/common/src/reason_codes/reason_codes_v1.ts' \
    '(reason_code|reasonCode|reason)\s*:\s*["'\'']' \
    packages 2>/dev/null || true)"
else
  HITS="$(find packages -path '*/src/*.ts' ! -path 'packages/common/src/reason_codes/reason_codes_v1.ts' -exec grep -nE '(reason_code|reasonCode|reason)[[:space:]]*:[[:space:]]*["'\'']' {} + 2>/dev/null || true)"
fi

if [ -n "$HITS" ]; then
  echo "FAIL: reason_code string literal detected in production code"
  echo "$HITS"
  exit 1
fi

# enum이 완전 미사용이 되지 않게 최소 사용 흔적 확인
if have_rg; then
  rg -n 'ReasonCodeV1|REASON_CODES_V1' packages >/dev/null
else
  grep -RnE 'ReasonCodeV1|REASON_CODES_V1' packages >/dev/null
fi

REASON_CODE_SINGLE_SOURCE_OK=1
REASON_CODE_DRIFT_GUARD_OK=1
exit 0

