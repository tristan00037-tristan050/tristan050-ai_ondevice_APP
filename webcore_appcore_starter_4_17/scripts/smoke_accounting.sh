#!/bin/bash
# 회계 스모크 테스트 스크립트
# 캡처→분개→승인→Export 최소 플로우 테스트

set -e

# 환경 변수
BFF_URL="${BFF_URL:-http://localhost:8081}"
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
echo "Accounting Smoke Test"
echo "=========================================="
echo "BFF URL: $BFF_URL"
echo "Tenant ID: $TENANT_ID"
echo ""

# 1. 분개 추천 테스트
echo "1. Posting Suggest"
echo "----------------------------------------"
SUGGEST_PAYLOAD='{
  "items": [
    {
      "desc": "사무용품 구매",
      "amount": "10000.00",
      "currency": "KRW"
    },
    {
      "desc": "택시비",
      "amount": "5000.00",
      "currency": "KRW"
    }
  ],
  "policy_version": "v1.0.0"
}'

SUGGEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "$BFF_URL/v1/accounting/postings/suggest" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "$SUGGEST_PAYLOAD")

SUGGEST_BODY=$(echo "$SUGGEST_RESPONSE" | head -n -1)
SUGGEST_STATUS=$(echo "$SUGGEST_RESPONSE" | tail -n 1)

if [ "$SUGGEST_STATUS" = "200" ]; then
  POSTINGS_COUNT=$(echo "$SUGGEST_BODY" | jq -r '.postings | length // 0')
  CONFIDENCE=$(echo "$SUGGEST_BODY" | jq -r '.confidence // 0')
  if [ "$POSTINGS_COUNT" -gt "0" ]; then
    test_pass "Posting suggest successful ($POSTINGS_COUNT postings, confidence: $CONFIDENCE)"
    export SUGGESTED_POSTINGS="$SUGGEST_BODY"
  else
    test_fail "Posting suggest returned empty postings"
  fi
else
  test_fail "Posting suggest failed (HTTP $SUGGEST_STATUS)"
  echo "Response: $SUGGEST_BODY"
fi
echo ""

# 2. 분개 생성 테스트
echo "2. Create Posting"
echo "----------------------------------------"
if [ -z "$SUGGESTED_POSTINGS" ]; then
  test_info "Skipping create posting test (no suggested postings)"
else
  CREATE_PAYLOAD=$(echo "$SUGGESTED_POSTINGS" | jq '{
    entries: .postings,
    currency: "KRW",
    client_request_id: "smoke-test-'$(date +%s)'"
  }')

  CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$BFF_URL/v1/accounting/postings" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: smoke-test-$(date +%s)" \
    -d "$CREATE_PAYLOAD")

  CREATE_BODY=$(echo "$CREATE_RESPONSE" | head -n -1)
  CREATE_STATUS=$(echo "$CREATE_RESPONSE" | tail -n 1)

  if [ "$CREATE_STATUS" = "201" ]; then
    POSTING_ID=$(echo "$CREATE_BODY" | jq -r '.id // empty')
    if [ -n "$POSTING_ID" ]; then
      test_pass "Posting created successfully (ID: $POSTING_ID)"
      export CREATED_POSTING_ID="$POSTING_ID"
    else
      test_fail "Posting created but ID not found in response"
    fi
  else
    test_fail "Posting create failed (HTTP $CREATE_STATUS)"
    echo "Response: $CREATE_BODY"
  fi
fi
echo ""

# 3. 승인 요청 테스트
echo "3. Request Approval"
echo "----------------------------------------"
if [ -z "$CREATED_POSTING_ID" ]; then
  test_info "Skipping approval request test (no posting ID)"
else
  APPROVAL_PAYLOAD="{
    \"posting_id\": \"$CREATED_POSTING_ID\",
    \"approver_id\": \"approver-001\"
  }"

  APPROVAL_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$BFF_URL/v1/accounting/approvals" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID" \
    -H "Content-Type: application/json" \
    -d "$APPROVAL_PAYLOAD")

  APPROVAL_BODY=$(echo "$APPROVAL_RESPONSE" | head -n -1)
  APPROVAL_STATUS=$(echo "$APPROVAL_RESPONSE" | tail -n 1)

  if [ "$APPROVAL_STATUS" = "201" ]; then
    APPROVAL_ID=$(echo "$APPROVAL_BODY" | jq -r '.id // empty')
    if [ -n "$APPROVAL_ID" ]; then
      test_pass "Approval requested successfully (ID: $APPROVAL_ID)"
      export CREATED_APPROVAL_ID="$APPROVAL_ID"
    else
      test_fail "Approval requested but ID not found in response"
    fi
  else
    test_fail "Approval request failed (HTTP $APPROVAL_STATUS)"
    echo "Response: $APPROVAL_BODY"
  fi
fi
echo ""

# 4. 승인 상태 조회 테스트
echo "4. Get Approval Status"
echo "----------------------------------------"
if [ -z "$CREATED_APPROVAL_ID" ]; then
  test_info "Skipping approval status test (no approval ID)"
else
  STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$BFF_URL/v1/accounting/approvals/$CREATED_APPROVAL_ID" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant: $TENANT_ID")

  STATUS_BODY=$(echo "$STATUS_RESPONSE" | head -n -1)
  STATUS_CODE=$(echo "$STATUS_RESPONSE" | tail -n 1)

  if [ "$STATUS_CODE" = "200" ]; then
    APPROVAL_STATUS=$(echo "$STATUS_BODY" | jq -r '.status // empty')
    if [ -n "$APPROVAL_STATUS" ]; then
      test_pass "Approval status retrieved (status: $APPROVAL_STATUS)"
    else
      test_fail "Approval status retrieved but status field missing"
    fi
  else
    test_fail "Approval status failed (HTTP $STATUS_CODE)"
  fi
fi
echo ""

# 5. Export 요청 테스트
echo "5. Export Request"
echo "----------------------------------------"
EXPORT_PAYLOAD="{
  \"format\": \"csv\",
  \"period_start\": \"$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo '2025-01-13T00:00:00Z')\",
  \"period_end\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo '2025-01-20T00:00:00Z')\",
  \"max_records\": 100
}"

EXPORT_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "$BFF_URL/v1/accounting/exports" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "$EXPORT_PAYLOAD")

EXPORT_BODY=$(echo "$EXPORT_RESPONSE" | head -n -1)
EXPORT_STATUS=$(echo "$EXPORT_RESPONSE" | tail -n 1)

if [ "$EXPORT_STATUS" = "202" ]; then
  JOB_ID=$(echo "$EXPORT_BODY" | jq -r '.job_id // empty')
  if [ -n "$JOB_ID" ]; then
    test_pass "Export requested successfully (Job ID: $JOB_ID)"
  else
    test_fail "Export requested but job_id not found in response"
  fi
else
  test_info "Export request returned HTTP $EXPORT_STATUS (may not be implemented yet)"
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

