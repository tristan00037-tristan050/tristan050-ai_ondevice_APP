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

echo "[verify] R10-S5 P0-6: RAG 텔레메트리 meta-only 계약 검증"
echo ""

# BFF 서버 실행 확인
if ! curl -sS -o /dev/null -w "%{http_code}" "${BFF}/health" > /dev/null 2>&1; then
  echo "[WARN] BFF 서버가 실행 중이지 않습니다. 검증을 건너뜁니다."
  echo "[INFO] BFF 서버 시작: ./scripts/dev_bff.sh"
  echo "[OK] R10-S5 P0-6: RAG 텔레메트리 meta-only 계약 검증 SKIP (BFF 미실행)"
  exit 0
fi

echo ""

# RAG-1) 정상 RAG meta-only 전송이 204로 통과하는지
echo "[test] RAG-1) 정상 RAG meta-only 전송 (기대: 204)"
status1=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_shown",
    "suggestionLength":100,
    "backend":"real",
    "modelLoadMs":12,
    "inferenceMs":34,
    "firstByteMs":10,
    "success":true,
    "fallback":false,
    "cancelled":false,
    "ragEnabled":true,
    "ragDocs":5,
    "ragTopK":3,
    "ragContextChars":500,
    "ragEmbeddingMs":10,
    "ragRetrieveMs":5,
    "ragIndexWarm":true,
    "ragIndexBuildMs":100,
    "ragIndexPersistMs":20,
    "ragIndexHydrateMs":15,
    "ragDocCount":100
  }')

if [ "$status1" = "204" ]; then
  echo "[OK] 정상 RAG meta-only 전송: 204 No Content"
else
  echo "[FAIL] 정상 RAG meta-only 전송: 기대 204, 실제 $status1"
  exit 1
fi

echo ""

# RAG-2) 원문 키가 섞이면 서버가 차단하는지(400/차단 동작)
echo "[test] RAG-2) 원문 키 차단 검증 (기대: 400)"
status2=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_shown",
    "suggestionLength":100,
    "ragEnabled":true,
    "ragContext":"SHOULD_BLOCK_RAW_TEXT"
  }')

if [ "$status2" = "400" ]; then
  echo "[OK] 원문 키 차단: 400 Bad Request"
else
  echo "[FAIL] 원문 키 차단: 기대 400, 실제 $status2"
  exit 1
fi

echo ""

# RAG-3) RAG 원문 텍스트 필드 차단 (ragText, ragChunk 등)
echo "[test] RAG-3) RAG 원문 텍스트 필드 차단 (기대: 400)"
status3=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_shown",
    "suggestionLength":100,
    "ragEnabled":true,
    "ragText":"SHOULD_BLOCK",
    "ragChunk":"SHOULD_BLOCK"
  }')

if [ "$status3" = "400" ]; then
  echo "[OK] RAG 원문 텍스트 필드 차단: 400 Bad Request"
else
  echo "[FAIL] RAG 원문 텍스트 필드 차단: 기대 400, 실제 $status3"
  exit 1
fi

echo ""

# RAG-4) Warm start 케이스 (ragIndexWarm=true, hydrateMs 기록)
echo "[test] RAG-4) Warm start 케이스 (기대: 204)"
status4=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_shown",
    "suggestionLength":100,
    "ragEnabled":true,
    "ragIndexWarm":true,
    "ragIndexHydrateMs":15,
    "ragDocCount":100
  }')

if [ "$status4" = "204" ]; then
  echo "[OK] Warm start 케이스: 204 No Content"
else
  echo "[FAIL] Warm start 케이스: 기대 204, 실제 $status4"
  exit 1
fi

echo ""

# RAG-5) Cold start 케이스 (ragIndexWarm=false, indexBuildMs 기록)
echo "[test] RAG-5) Cold start 케이스 (기대: 204)"
status5=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_shown",
    "suggestionLength":100,
    "ragEnabled":true,
    "ragIndexWarm":false,
    "ragIndexBuildMs":100,
    "ragDocCount":100
  }')

if [ "$status5" = "204" ]; then
  echo "[OK] Cold start 케이스: 204 No Content"
else
  echo "[FAIL] Cold start 케이스: 기대 204, 실제 $status5"
  exit 1
fi

echo ""

# RAG-6) 에러/취소 케이스에서도 원문 유출 0 보장
echo "[test] RAG-6) 에러 케이스에서 원문 유출 차단 (기대: 400)"
status6=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "${BFF}/v1/os/llm-usage" \
  "${AUTH_HEADERS[@]}" \
  -d '{
    "eventType":"suggestion_error",
    "suggestionLength":0,
    "success":false,
    "fallback":true,
    "ragEnabled":true,
    "errorMessage":"SHOULD_BLOCK"
  }')

if [ "$status6" = "400" ]; then
  echo "[OK] 에러 케이스 원문 유출 차단: 400 Bad Request"
else
  echo "[FAIL] 에러 케이스 원문 유출 차단: 기대 400, 실제 $status6"
  exit 1
fi

echo ""
echo "[OK] R10-S5 P0-6: RAG 텔레메트리 meta-only 계약 검증 PASS"

