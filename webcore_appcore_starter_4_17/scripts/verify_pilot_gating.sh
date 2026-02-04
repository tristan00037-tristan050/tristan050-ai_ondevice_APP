#!/bin/bash
# 파일럿 게이팅 검증 스크립트
# 사용법: ./scripts/verify_pilot_gating.sh [BFF_URL]

set -e

BFF_URL=${1:-"http://localhost:8081"}
PILOT_TENANTS=("default" "pilot-a")
NON_PILOT_TENANTS=("pilot-b" "test-tenant" "unauthorized")

echo "🔍 파일럿 게이팅 검증"
echo "   BFF URL: $BFF_URL"
echo ""

# 헬스 체크
echo "1. 헬스 체크..."
if curl -sf "$BFF_URL/health" > /dev/null; then
  echo "   ✅ 헬스 체크 통과"
else
  echo "   ❌ 헬스 체크 실패"
  exit 1
fi
echo ""

# 파일럿 테넌트 접근 확인
echo "2. 파일럿 테넌트 접근 확인..."
PILOT_PASS=0
PILOT_FAIL=0

for tenant in "${PILOT_TENANTS[@]}"; do
  response=$(curl -s -w "\n%{http_code}" \
    -H "X-Tenant: $tenant" \
    -H "X-User-Role: operator" \
    -H "X-User-Id: pilot-user" \
    "$BFF_URL/v1/accounting/audit?page=1&page_size=1" 2>/dev/null || echo -e "\n000")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -1)
  
  if [ "$http_code" = "200" ] || [ "$http_code" = "403" ]; then
    # 200 (성공) 또는 403 (role 제한)은 정상
    if echo "$body" | grep -q "TENANT_NOT_ENABLED"; then
      echo "   ❌ $tenant: 차단됨 (예상: 허용)"
      PILOT_FAIL=$((PILOT_FAIL + 1))
    else
      echo "   ✅ $tenant: 접근 가능 (HTTP $http_code)"
      PILOT_PASS=$((PILOT_PASS + 1))
    fi
  else
    echo "   ⚠️  $tenant: HTTP $http_code (예상: 200 또는 403)"
  fi
done
echo ""

# 비파일럿 테넌트 차단 확인
echo "3. 비파일럿 테넌트 차단 확인..."
NON_PILOT_PASS=0
NON_PILOT_FAIL=0

for tenant in "${NON_PILOT_TENANTS[@]}"; do
  response=$(curl -s -w "\n%{http_code}" \
    -H "X-Tenant: $tenant" \
    -H "X-User-Role: operator" \
    -H "X-User-Id: test-user" \
    "$BFF_URL/v1/accounting/audit?page=1&page_size=1" 2>/dev/null || echo -e "\n000")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -1)
  
  if [ "$http_code" = "403" ] && echo "$body" | grep -q "TENANT_NOT_ENABLED"; then
    echo "   ✅ $tenant: 차단됨 (예상: 403 TENANT_NOT_ENABLED)"
    NON_PILOT_PASS=$((NON_PILOT_PASS + 1))
  else
    echo "   ❌ $tenant: HTTP $http_code (예상: 403 TENANT_NOT_ENABLED)"
    if [ "$http_code" != "000" ]; then
      echo "      응답: $body"
    fi
    NON_PILOT_FAIL=$((NON_PILOT_FAIL + 1))
  fi
done
echo ""

# 결과 요약
echo "=" | tr '=' '='
echo "📊 검증 결과 요약"
echo "=" | tr '=' '='
echo "파일럿 테넌트 접근: $PILOT_PASS 성공, $PILOT_FAIL 실패"
echo "비파일럿 테넌트 차단: $NON_PILOT_PASS 성공, $NON_PILOT_FAIL 실패"
echo ""

if [ $PILOT_FAIL -eq 0 ] && [ $NON_PILOT_PASS -gt 0 ]; then
  echo "✅ 파일럿 게이팅 정상 작동"
  exit 0
else
  echo "❌ 파일럿 게이팅 검증 실패"
  echo ""
  echo "확인 사항:"
  echo "  1. OS_TENANT_ALLOWLIST_JSON 환경변수 설정 확인"
  echo "  2. BFF 재시작 확인"
  echo "  3. 로그 확인: kubectl logs -n accounting deployment/bff-accounting"
  exit 1
fi

