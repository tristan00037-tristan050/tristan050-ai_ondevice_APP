#!/usr/bin/env bash
set -euo pipefail

# Track A-2: META_ONLY_VALIDATOR_SINGLE_SOURCE 검증
# 목표: meta-only validator를 단일 소스로 통합, 중복 구현 0, 우회 경로 0, 저장 후 필터 0 봉인

META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=0
META_ONLY_VALIDATOR_NO_DUPLICATION_OK=0
META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=0

cleanup() {
  echo "META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=${META_ONLY_VALIDATOR_SINGLE_SOURCE_OK}"
  echo "META_ONLY_VALIDATOR_NO_DUPLICATION_OK=${META_ONLY_VALIDATOR_NO_DUPLICATION_OK}"
  echo "META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=${META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK}"
  if [[ "${META_ONLY_VALIDATOR_SINGLE_SOURCE_OK}" == "1" ]] && \
     [[ "${META_ONLY_VALIDATOR_NO_DUPLICATION_OK}" == "1" ]] && \
     [[ "${META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# rg 없으면 grep 폴백 (설치 금지)
run_q() { if command -v rg >/dev/null 2>&1; then rg -q "$@"; else grep -qE "$1" "$2" 2>/dev/null; fi; }
run_n() { if command -v rg >/dev/null 2>&1; then rg -n "$@"; else grep -nE "$1" "$2" 2>/dev/null || true; fi; }

# 단일 소스 validator 파일 (CommonJS 또는 TypeScript)
SINGLE_SOURCE_CJS="packages/common/meta_only/validator_v1.cjs"
SINGLE_SOURCE_TS="packages/common/meta_only/validator_v1.ts"

# 단일 소스 런타임 파일(.cjs) 존재는 필수
test -f "$SINGLE_SOURCE_CJS" || { META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=0; exit 1; }
META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=1

if [[ -f "$SINGLE_SOURCE_CJS" ]]; then
  SINGLE_SOURCE="$SINGLE_SOURCE_CJS"
elif [[ -f "$SINGLE_SOURCE_TS" ]]; then
  SINGLE_SOURCE="$SINGLE_SOURCE_TS"
else
  echo "BLOCK: missing single source: $SINGLE_SOURCE_CJS or $SINGLE_SOURCE_TS"
  exit 1
fi

# 1) 단일 소스 파일 존재 확인
test -s "$SINGLE_SOURCE" || { echo "BLOCK: missing single source: $SINGLE_SOURCE"; exit 1; }

# assertMetaOnly, validateMetaOnlyOrThrow 함수가 존재하는지 확인
if ! run_q "(function\s+assertMetaOnly|function\s+validateMetaOnlyOrThrow)" "$SINGLE_SOURCE"; then
  echo "BLOCK: assertMetaOnly or validateMetaOnlyOrThrow function not found in single source"
  exit 1
fi

META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=1

# 2) 중복 구현 탐지 (정적)
# 금지 파일 목록 (중복 구현이 있으면 안 되는 파일)
FORBIDDEN_DUPLICATE_FILES=(
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts"
  "webcore_appcore_starter_4_17/packages/butler-runtime/src/server.mjs"
  "scripts/ops_hub/trace_service_store_v1.cjs"
  "scripts/ops_hub/trace_realpath_store_v1.cjs"
)

DUPLICATE_FOUND=0

for file in "${FORBIDDEN_DUPLICATE_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    continue
  fi

  # assertMetaOnly 함수 정의가 있는지 확인 (중복 구현 - 금지)
  if run_n "function\s+assertMetaOnly" "$file" | grep -vE '^\s*#' | grep -vE '^\s*//' | grep -vE 'import|from|require' >/dev/null 2>&1; then
    echo "BLOCK: duplicate assertMetaOnly implementation found in $file (must use single source)"
    run_n "function\s+assertMetaOnly" "$file" | head -3
    DUPLICATE_FOUND=1
    continue
  fi

  # validateMetaOnlyOrThrow 함수 정의가 있는지 확인
  FUNC_DEF=$(run_n "export\s+function\s+validateMetaOnlyOrThrow|function\s+validateMetaOnlyOrThrow" "$file" | grep -vE '^\s*#' | grep -vE '^\s*//' | grep -vE 'import|from|require' | head -1 || echo "")
  
  if [[ -n "$FUNC_DEF" ]]; then
    # 단일 소스 import 확인
    HAS_SINGLE_SOURCE_IMPORT=0
    if grep -q "validator_v1" "$file" 2>/dev/null; then
      HAS_SINGLE_SOURCE_IMPORT=1
    fi

    # 단일 소스 호출 확인
    HAS_SINGLE_SOURCE_CALL=0
    # 함수 정의 이후에 단일 소스 validator 호출 확인
    FUNC_LINE=$(echo "$FUNC_DEF" | cut -d: -f1)
    if [[ -n "$FUNC_LINE" ]]; then
      TOTAL_LINES=$(wc -l < "$file" || echo "0")
      END_LINE=$((FUNC_LINE + 30))
      if [[ "$END_LINE" -gt "$TOTAL_LINES" ]]; then
        END_LINE="$TOTAL_LINES"
      fi
      # 함수 내부에서 단일 소스 validator 호출 확인
      FUNC_CONTENT=$(sed -n "${FUNC_LINE},${END_LINE}p" "$file")
      if echo "$FUNC_CONTENT" | grep -E "validateMetaOnlyOrThrowSingleSource|assertMetaOnly" >/dev/null 2>&1; then
        HAS_SINGLE_SOURCE_CALL=1
      fi
    fi

    # PASS 규칙: (assertMetaOnly OR validateMetaOnlyOrThrow) AND validator_v1 가 모두 만족되면 PASS
    if [[ "$HAS_SINGLE_SOURCE_IMPORT" -eq 1 ]] && [[ "$HAS_SINGLE_SOURCE_CALL" -eq 1 ]]; then
      continue  # 래퍼 함수는 허용
    fi

    echo "BLOCK: validateMetaOnlyOrThrow found in $file but not using single source (import=$HAS_SINGLE_SOURCE_IMPORT, call=$HAS_SINGLE_SOURCE_CALL)"
    echo "$FUNC_DEF"
    DUPLICATE_FOUND=1
  fi
done

if [[ "$DUPLICATE_FOUND" -eq 1 ]]; then
  exit 1
fi

META_ONLY_VALIDATOR_NO_DUPLICATION_OK=1

exit 0
