#!/bin/bash
# Collector 스모크 테스트 스크립트
# 헬스 체크, 인제스트, 리포트 조회, 서명, 번들 다운로드 테스트

set -e

# 환경 변수
COLLECTOR_URL="${COLLECTOR_URL:-http://localhost:9090}"
API_KEY="${API_KEY:-collector-key}"
TENANT_ID="${TENANT_ID:-default}"

# 색상 출력
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 테스트 카운터
PASSED=0
FAILED=0

# 테스트 헬퍼 함수
test_pass() {
  echo -e "${GREEN}✅ PASS:${NC} $1"
  ((PASSED++))
}

test_fail() {
  echo -e "${RED}❌ FAIL:${NC} $1"
  ((FAILED++))
}

test_info() {
  echo -e "${YELLOW}ℹ️  INFO:${NC} $1"
}

# 헤더 출력
echo "=========================================="
echo "Collector Smoke Test"
echo "=========================================="
echo "Collector URL: $COLLECTOR_URL"
echo "Tenant ID: $TENANT_ID"
echo ""

# 1. 헬스 체크
echo "1. Health Check"
echo "----------------------------------------"
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$COLLECTOR_URL/health")
HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)
HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | tail -n 1)

if [ "$HEALTH_STATUS" = "200" ]; then
  DB_STATUS=$(echo "$HEALTH_BODY" | jq -r '.database // "unknown"')
  if [ "$DB_STATUS" = "connected" ]; then
    test_pass "Health check passed (database connected)"
  else
    test_fail "Health check passed but database disconnected"
  fi
else
  test_fail "Health check failed (HTTP $HEALTH_STATUS)"
fi
echo ""

# 2. 메트릭 엔드포인트
echo "2. Metrics Endpoint"
echo "----------------------------------------"
METRICS_RESPONSE=$(curl -s -w "\n%{http_code}" "$COLLECTOR_URL/metrics")
METRICS_STATUS=$(echo "$METRICS_RESPONSE" | tail -n 1)

if [ "$METRICS_STATUS" = "200" ]; then
  METRICS_COUNT=$(echo "$METRICS_RESPONSE" | head -n -1 | grep -c "collector_" || echo "0")
  if [ "$METRICS_COUNT" -gt "0" ]; then
    test_pass "Metrics endpoint accessible ($METRICS_COUNT metrics found)"
  else
    test_fail "Metrics endpoint accessible but no metrics found"
  fi
else
  test_fail "Metrics endpoint failed (HTTP $METRICS_STATUS)"
fi
echo ""

# 3. 리포트 인제스트
echo "3. Report Ingest"
echo "----------------------------------------"
INGEST_PAYLOAD='{
  "status": {
    "api": "pass",
    "jwks": "pass"
  },
  "policy": {
    "policy_version": "v1.0.0",
    "evaluations": [
      {
        "severity": "info",
        "rule": "test-rule",
        "result": "pass"
      }
    ]
  },
  "diff": {},
  "notes": []
}'

INGEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "$COLLECTOR_URL/ingest/qc" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "$INGEST_PAYLOAD")

INGEST_BODY=$(echo "$INGEST_RESPONSE" | head -n -1)
INGEST_STATUS=$(echo "$INGEST_RESPONSE" | tail -n 1)

if [ "$INGEST_STATUS" = "201" ]; then
  REPORT_ID=$(echo "$INGEST_BODY" | jq -r '.id // empty')
  if [ -n "$REPORT_ID" ]; then
    test_pass "Report ingested successfully (ID: $REPORT_ID)"
    export SMOKE_TEST_REPORT_ID="$REPORT_ID"
  else
    test_fail "Report ingested but ID not found in response"
  fi
else
  test_fail "Report ingest failed (HTTP $INGEST_STATUS)"
  echo "Response: $INGEST_BODY"
fi
echo ""

# 4. 리포트 목록 조회
echo "4. Report List"
echo "----------------------------------------"
if [ -z "$SMOKE_TEST_REPORT_ID" ]; then
  test_info "Skipping report list test (no report ID)"
else
  REPORTS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$COLLECTOR_URL/reports" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID")

  REPORTS_BODY=$(echo "$REPORTS_RESPONSE" | head -n -1)
  REPORTS_STATUS=$(echo "$REPORTS_RESPONSE" | tail -n 1)

  if [ "$REPORTS_STATUS" = "200" ]; then
    REPORTS_COUNT=$(echo "$REPORTS_BODY" | jq -r '.reports | length // 0')
    if [ "$REPORTS_COUNT" -gt "0" ]; then
      test_pass "Report list retrieved ($REPORTS_COUNT reports)"
    else
      test_fail "Report list retrieved but empty"
    fi
  else
    test_fail "Report list failed (HTTP $REPORTS_STATUS)"
  fi
fi
echo ""

# 5. 리포트 상세 조회
echo "5. Report Detail"
echo "----------------------------------------"
if [ -z "$SMOKE_TEST_REPORT_ID" ]; then
  test_info "Skipping report detail test (no report ID)"
else
  REPORT_RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$COLLECTOR_URL/reports/$SMOKE_TEST_REPORT_ID" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID")

  REPORT_BODY=$(echo "$REPORT_RESPONSE" | head -n -1)
  REPORT_STATUS=$(echo "$REPORT_RESPONSE" | tail -n 1)

  if [ "$REPORT_STATUS" = "200" ]; then
    REPORT_ID_FOUND=$(echo "$REPORT_BODY" | jq -r '.id // empty')
    if [ "$REPORT_ID_FOUND" = "$SMOKE_TEST_REPORT_ID" ]; then
      test_pass "Report detail retrieved (ID: $SMOKE_TEST_REPORT_ID)"
    else
      test_fail "Report detail retrieved but ID mismatch"
    fi
  else
    test_fail "Report detail failed (HTTP $REPORT_STATUS)"
  fi
fi
echo ""

# 6. 리포트 서명
echo "6. Report Sign"
echo "----------------------------------------"
if [ -z "$SMOKE_TEST_REPORT_ID" ]; then
  test_info "Skipping report sign test (no report ID)"
else
  SIGN_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$COLLECTOR_URL/reports/$SMOKE_TEST_REPORT_ID/sign" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID")

  SIGN_BODY=$(echo "$SIGN_RESPONSE" | head -n -1)
  SIGN_STATUS=$(echo "$SIGN_RESPONSE" | tail -n 1)

  if [ "$SIGN_STATUS" = "200" ]; then
    TOKEN=$(echo "$SIGN_BODY" | jq -r '.token // empty')
    if [ -n "$TOKEN" ]; then
      test_pass "Report signed successfully (token: ${TOKEN:0:16}...)"
      export SMOKE_TEST_TOKEN="$TOKEN"
    else
      test_fail "Report signed but token not found in response"
    fi
  else
    test_fail "Report sign failed (HTTP $SIGN_STATUS)"
  fi
fi
echo ""

# 7. 번들 다운로드
echo "7. Bundle Download"
echo "----------------------------------------"
if [ -z "$SMOKE_TEST_REPORT_ID" ] || [ -z "$SMOKE_TEST_TOKEN" ]; then
  test_info "Skipping bundle download test (no report ID or token)"
else
  BUNDLE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -o /tmp/smoke_test_bundle.zip \
    "$COLLECTOR_URL/reports/$SMOKE_TEST_REPORT_ID/bundle.zip?token=$SMOKE_TEST_TOKEN" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID")

  BUNDLE_STATUS=$(echo "$BUNDLE_RESPONSE" | tail -n 1)

  if [ "$BUNDLE_STATUS" = "200" ]; then
    if [ -f "/tmp/smoke_test_bundle.zip" ] && [ -s "/tmp/smoke_test_bundle.zip" ]; then
      BUNDLE_SIZE=$(stat -f%z /tmp/smoke_test_bundle.zip 2>/dev/null || stat -c%s /tmp/smoke_test_bundle.zip 2>/dev/null || echo "0")
      if [ "$BUNDLE_SIZE" -gt "0" ]; then
        test_pass "Bundle downloaded successfully (size: $BUNDLE_SIZE bytes)"
        rm -f /tmp/smoke_test_bundle.zip
      else
        test_fail "Bundle downloaded but file is empty"
      fi
    else
      test_fail "Bundle download failed (file not created)"
    fi
  else
    test_fail "Bundle download failed (HTTP $BUNDLE_STATUS)"
  fi
fi
echo ""

# 8. 타임라인 조회
echo "8. Timeline"
echo "----------------------------------------"
TIMELINE_RESPONSE=$(curl -s -w "\n%{http_code}" \
  "$COLLECTOR_URL/timeline?window_h=24" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID")

TIMELINE_BODY=$(echo "$TIMELINE_RESPONSE" | head -n -1)
TIMELINE_STATUS=$(echo "$TIMELINE_RESPONSE" | tail -n 1)

if [ "$TIMELINE_STATUS" = "200" ]; then
  BUCKETS_COUNT=$(echo "$TIMELINE_BODY" | jq -r '.buckets | length // 0')
  if [ "$BUCKETS_COUNT" -ge "0" ]; then
    test_pass "Timeline retrieved ($BUCKETS_COUNT buckets)"
  else
    test_fail "Timeline retrieved but invalid format"
  fi
else
  test_fail "Timeline failed (HTTP $TIMELINE_STATUS)"
fi
echo ""

# 9. Rate Limiting 테스트 (선택사항)
echo "9. Rate Limiting (Optional)"
echo "----------------------------------------"
RATE_LIMIT_TEST_COUNT=0
RATE_LIMIT_429_COUNT=0

for i in {1..110}; do
  RATE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$COLLECTOR_URL/health" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID" 2>/dev/null)
  RATE_STATUS=$(echo "$RATE_RESPONSE" | tail -n 1)
  
  if [ "$RATE_STATUS" = "429" ]; then
    ((RATE_LIMIT_429_COUNT++))
  fi
  ((RATE_LIMIT_TEST_COUNT++))
done

if [ "$RATE_LIMIT_429_COUNT" -gt "0" ]; then
  test_pass "Rate limiting working ($RATE_LIMIT_429_COUNT / $RATE_LIMIT_TEST_COUNT requests blocked)"
else
  test_info "Rate limiting not triggered (may need adjustment)"
fi
echo ""

# 결과 요약
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $PASSED"
echo -e "${RED}Failed:${NC} $FAILED"
echo ""

if [ "$FAILED" -eq "0" ]; then
  echo -e "${GREEN}✅ All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ Some tests failed!${NC}"
  exit 1
fi

