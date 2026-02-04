#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://127.0.0.1:8081}"
AUTH_HEADERS=(
  -H "Content-Type: application/json"
  -H "X-Tenant: default"
  -H "X-User-Id: hud-user-1"
  -H "X-User-Role: operator"
  -H "X-Api-Key: collector-key:operator"
)

echo "[verify] C. 성능 메타 KPI meta-only 계약 검증"
echo ""

# C-1) 정상 meta-only 전송이 204로 통과하는지
echo "[test] C-1) 정상 meta-only 전송 (기대: 204)"
status1=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"qa_trigger_llm_usage",
    "suggestionLength":0,
    "backend":"real",
    "modelLoadMs":12,
    "inferenceMs":34,
    "firstByteMs":10,
    "success":true,
    "fallback":false,
    "cancelled":false
  }')

if [ "$status1" = "204" ]; then
  echo "[OK] 정상 meta-only 전송: 204 No Content"
else
  echo "[FAIL] 정상 meta-only 전송: 기대 204, 실제 $status1"
  exit 1
fi

echo ""

# C-2) 원문 키가 섞이면 서버가 차단하는지(400/차단 동작)
echo "[test] C-2) 원문 키 차단 검증 (기대: 400)"
status2=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"qa_trigger_llm_usage",
    "suggestionLength":0,
    "prompt":"SHOULD_BLOCK"
  }')

if [ "$status2" = "400" ]; then
  echo "[OK] 원문 키 차단: 400 Bad Request"
else
  echo "[FAIL] 원문 키 차단: 기대 400, 실제 $status2"
  exit 1
fi

echo ""
echo "[OK] C. 성능 메타 KPI meta-only 계약 검증 PASS"

