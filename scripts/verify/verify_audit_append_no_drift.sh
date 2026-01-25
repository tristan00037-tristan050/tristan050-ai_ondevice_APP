#!/usr/bin/env bash
set -euo pipefail

TS="webcore_appcore_starter_4_17/backend/model_registry/services/audit_append.ts"
JS="webcore_appcore_starter_4_17/backend/model_registry/services/audit_append.js"

# 둘 중 하나만 있으면 PASS (단일 소스 방향)
if [ ! -f "$TS" ] || [ ! -f "$JS" ]; then
  echo "OK: AUDIT_APPEND_SINGLE_SOURCE_OR_MISSING=1"
  echo "AUDIT_APPEND_NO_DRIFT_OK=1"
  exit 0
fi

# 둘 다 있으면, 최소한의 동일성(핵심 함수명/컨셉 키워드)이 동시에 존재해야 한다.
# 실제 키워드는 프로젝트마다 다를 수 있어, 우선 "드리프트 발생 시 가장 먼저 깨지는 핵심 단서"를 잡는다.
needles=(
  "appendAuditV2"
  "hashActorId"
  "meta-only"
)

for n in "${needles[@]}"; do
  grep -nF -- "$n" "$TS" >/dev/null || { echo "BLOCK: TS missing token: $n"; echo "AUDIT_APPEND_NO_DRIFT_OK=0"; exit 1; }
  grep -nF -- "$n" "$JS" >/dev/null || { echo "BLOCK: JS missing token: $n"; echo "AUDIT_APPEND_NO_DRIFT_OK=0"; exit 1; }
done

echo "OK: AUDIT_APPEND_DUAL_IMPL_GUARDED=1"
echo "AUDIT_APPEND_NO_DRIFT_OK=1"
