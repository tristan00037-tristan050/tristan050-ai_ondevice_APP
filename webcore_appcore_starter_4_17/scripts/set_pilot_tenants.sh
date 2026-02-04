#!/bin/bash
# 파일럿 테넌트 설정 스크립트
# 사용법: ./scripts/set_pilot_tenants.sh default pilot-a

set -e

TENANTS=("$@")

if [ ${#TENANTS[@]} -eq 0 ]; then
  echo "❌ 오류: 테넌트 목록이 필요합니다."
  echo ""
  echo "사용법:"
  echo "  ./scripts/set_pilot_tenants.sh <tenant1> <tenant2> ..."
  echo ""
  echo "예시:"
  echo "  ./scripts/set_pilot_tenants.sh default pilot-a"
  exit 1
fi

# JSON 배열 생성 (한 줄로 압축)
JSON_ARRAY=$(printf '%s\n' "${TENANTS[@]}" | jq -R . | jq -s -c .)

echo "🔄 파일럿 테넌트 설정"
echo "   테넌트: ${TENANTS[*]}"
echo "   JSON: $JSON_ARRAY"
echo ""

# Helm values 파일 업데이트
VALUES_FILE="charts/bff-accounting/values.yaml"

if [ ! -f "$VALUES_FILE" ]; then
  echo "❌ 오류: Helm values 파일을 찾을 수 없습니다: $VALUES_FILE"
  exit 1
fi

# OS_TENANT_ALLOWLIST_JSON이 이미 있으면 업데이트, 없으면 추가
if grep -q "OS_TENANT_ALLOWLIST_JSON" "$VALUES_FILE"; then
  # macOS와 Linux 모두 지원하는 sed 명령어
  # JSON을 이스케이프하여 sed 패턴에 안전하게 사용
  ESCAPED_JSON=$(echo "$JSON_ARRAY" | sed 's/[[\]/\\&/g' | sed "s/'/\\\'/g")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|OS_TENANT_ALLOWLIST_JSON:.*|OS_TENANT_ALLOWLIST_JSON: '$ESCAPED_JSON'|" "$VALUES_FILE"
  else
    sed -i "s|OS_TENANT_ALLOWLIST_JSON:.*|OS_TENANT_ALLOWLIST_JSON: '$ESCAPED_JSON'|" "$VALUES_FILE"
  fi
  echo "✅ Helm values 파일 업데이트 완료"
else
  # env 섹션에 추가
  ESCAPED_JSON=$(echo "$JSON_ARRAY" | sed 's/[[\]/\\&/g' | sed "s/'/\\\'/g")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "/OS_ROLE_MAP_JSON:/a\\
          OS_TENANT_ALLOWLIST_JSON: '$ESCAPED_JSON'
" "$VALUES_FILE"
  else
    sed -i "/OS_ROLE_MAP_JSON:/a OS_TENANT_ALLOWLIST_JSON: '$ESCAPED_JSON'" "$VALUES_FILE"
  fi
  echo "✅ Helm values 파일에 추가 완료"
fi

echo ""
echo "📋 다음 단계:"
echo "   1. Helm values 파일 확인:"
echo "      cat $VALUES_FILE | grep OS_TENANT_ALLOWLIST_JSON"
echo ""
echo "   2. Helm upgrade 실행:"
echo "      helm upgrade --install bff charts/bff-accounting --namespace accounting"
echo ""
echo "   3. 또는 로컬 테스트용 환경변수 설정:"
echo "      export OS_TENANT_ALLOWLIST_JSON='$JSON_ARRAY'"

