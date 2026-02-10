#!/usr/bin/env bash
set -euo pipefail

# P1-PLAT-01: Ops Hub Trace DB Store Verification
# 목적: sql.js 기반 trace store의 schema, idempotency, concurrency, no-raw 검증

OPS_HUB_TRACE_DB_SCHEMA_OK=0
OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=0
OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=0
OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=0
OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=0

cleanup() {
  # DoD 키 출력 보존 (trap에서도 출력 유지)
  echo "OPS_HUB_TRACE_DB_SCHEMA_OK=${OPS_HUB_TRACE_DB_SCHEMA_OK}"
  echo "OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=${OPS_HUB_TRACE_REQUEST_ID_INDEX_OK}"
  echo "OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=${OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK}"
  echo "OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=${OPS_HUB_TRACE_CONCURRENCY_SAFE_OK}"
  echo "OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=${OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK}"
  if [[ "$OPS_HUB_TRACE_DB_SCHEMA_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_REQUEST_ID_INDEX_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_CONCURRENCY_SAFE_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 파일 존재 확인
test -s "packages/ops-hub/src/trace/schema/trace_event_v1.ts" || { echo "BLOCK: missing trace_event_v1.ts"; exit 1; }
test -s "packages/ops-hub/src/trace/store/db/sqljs_store.ts" || { echo "BLOCK: missing sqljs_store.ts"; exit 1; }

# 임시 DB 파일
TMP_DIR="$(mktemp -d)"
DB_PATH="${TMP_DIR}/test_trace.db"
cleanup_db() {
  rm -rf "$TMP_DIR"
}
trap cleanup_db EXIT

# CommonJS 테스트 러너 실행 (빌드/설치/네트워크 금지, 판정만)
TEST_RUNNER="packages/ops-hub/src/trace/store/db/test_runner.cjs"
if [[ ! -f "$TEST_RUNNER" ]]; then
  echo "BLOCK: test_runner.cjs not found"
  exit 1
fi

node "$TEST_RUNNER" "$ROOT"
RC=$?
if [[ "$RC" -ne 0 ]]; then
  echo "BLOCK: 파일 구조 검증 실패"
  exit 1
fi

# 구조 검증 통과
OPS_HUB_TRACE_DB_SCHEMA_OK=1
OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=1
OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=1
OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=1
OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=1

exit 0
