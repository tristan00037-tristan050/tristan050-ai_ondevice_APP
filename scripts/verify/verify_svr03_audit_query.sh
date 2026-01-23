#!/usr/bin/env bash
set -euo pipefail

SVR03_AUDIT_QUERY_SMOKE_OK=0
SVR03_AUDIT_QUERY_FILTER_OK=0

cleanup() {
  echo "SVR03_AUDIT_QUERY_SMOKE_OK=${SVR03_AUDIT_QUERY_SMOKE_OK}"
  echo "SVR03_AUDIT_QUERY_FILTER_OK=${SVR03_AUDIT_QUERY_FILTER_OK}"
}
trap cleanup EXIT

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATA_DIR="webcore_appcore_starter_4_17/backend/model_registry/data"
mkdir -p "$DATA_DIR"

# 테스트용 별도 파일 사용 (기존 파일과 충돌 방지)
TEST_DATE="9999-12-31"
AUDIT_FILE="${DATA_DIR}/audit_${TEST_DATE}.json"

# 테스트 이벤트 생성
python3 - <<PY
import json,os,time
p="${AUDIT_FILE}"
events=[
  {"ts_ms": int(time.time()*1000), "action":"APPLY","result":"DENY","reason_code":"TEST_RC_A","key_id":"kA","sha256":"sA"},
  {"ts_ms": int(time.time()*1000), "action":"APPLY","result":"DENY","reason_code":"TEST_RC_B","key_id":"kB","sha256":"sB"},
]
with open(p,"w",encoding="utf-8") as f:
  json.dump(events,f)
PY

# 1) smoke: 기본 조회가 출력 1줄 이상을 내는지
OUT1="$(bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --date "$TEST_DATE" --limit 10 2>&1 || true)"
if echo "$OUT1" | grep -q '"reason_code":"TEST_RC_A"\|"reason_code":"TEST_RC_B"'; then
  SVR03_AUDIT_QUERY_SMOKE_OK=1
else
  echo "FAIL: smoke query produced no test events"
  echo "$OUT1" | head -20
  rm -f "$AUDIT_FILE"
  exit 1
fi

# 2) filter: reason_code=TEST_RC_A면 그 값만 나와야 함
OUT2="$(bash webcore_appcore_starter_4_17/scripts/ops/svr03_audit_query.sh --date "$TEST_DATE" --reason_code TEST_RC_A --limit 10 2>&1 || true)"
if echo "$OUT2" | grep -q '"reason_code":"TEST_RC_A"' && ! echo "$OUT2" | grep -q '"reason_code":"TEST_RC_B"'; then
  SVR03_AUDIT_QUERY_FILTER_OK=1
else
  echo "FAIL: filter did not work"
  echo "$OUT2" | head -20
  rm -f "$AUDIT_FILE"
  exit 1
fi

# 정리
rm -f "$AUDIT_FILE"

exit 0

