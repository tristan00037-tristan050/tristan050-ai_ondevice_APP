#!/bin/bash
# 파일럿 테넌트 환경변수 설정 스크립트
# 사용법: source ./scripts/set_pilot_env.sh default pilot-a
# 또는: . ./scripts/set_pilot_env.sh default pilot-a

TENANTS=("$@")

if [ ${#TENANTS[@]} -eq 0 ]; then
  echo "❌ 오류: 테넌트 목록이 필요합니다."
  echo ""
  echo "사용법:"
  echo "  source ./scripts/set_pilot_env.sh <tenant1> <tenant2> ..."
  echo "  # 또는"
  echo "  . ./scripts/set_pilot_env.sh <tenant1> <tenant2> ..."
  echo ""
  echo "예시:"
  echo "  source ./scripts/set_pilot_env.sh default pilot-a"
  echo ""
  echo "⚠️  주의: source 또는 . 명령어를 사용해야 현재 셸에 환경변수가 설정됩니다."
  return 2>/dev/null || exit 1
fi

# JSON 배열 생성 (한 줄로 압축)
JSON_ARRAY=$(printf '%s\n' "${TENANTS[@]}" | jq -R . | jq -s -c .)

# 환경변수 설정
export OS_TENANT_ALLOWLIST_JSON="$JSON_ARRAY"

echo "✅ 파일럿 테넌트 환경변수 설정 완료"
echo "   테넌트: ${TENANTS[*]}"
echo "   OS_TENANT_ALLOWLIST_JSON=$OS_TENANT_ALLOWLIST_JSON"
echo ""
echo "📋 사용 방법:"
echo "   이 환경변수는 현재 셸에서만 유효합니다."
echo "   BFF 실행 시 자동으로 적용됩니다."
echo ""
echo "   확인:"
echo "     echo \$OS_TENANT_ALLOWLIST_JSON"
echo ""
echo "   BFF 실행 예시:"
echo "     cd packages/bff-accounting"
echo "     npm run build"
echo "     node dist/index.js"

