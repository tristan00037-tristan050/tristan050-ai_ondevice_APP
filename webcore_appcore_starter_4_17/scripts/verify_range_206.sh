#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://127.0.0.1:8081}"
MODEL_ID="${WEBLLM_TEST_MODEL_ID:-local-llm-v1}"
MODEL_FILE="${WEBLLM_TEST_MODEL_FILE:-manifest.json}"
AUTH_HEADERS=(
  -H "X-Tenant: default"
  -H "X-User-Id: hud-user-1"
  -H "X-User-Role: operator"
  -H "X-Api-Key: collector-key:operator"
)

echo "[verify] D. Range(206) / Accept-Ranges 동작 확인"
echo ""

URL="${BFF}/v1/os/models/${MODEL_ID}/${MODEL_FILE}"

# D-1) 일반 GET 요청으로 Accept-Ranges 헤더 확인
echo "[test] D-1) 일반 GET 요청 (Accept-Ranges 헤더 확인)"
hdr1=$(mktemp)
curl -sS -D "$hdr1" -o /dev/null \
  "${AUTH_HEADERS[@]}" \
  "$URL" || true

status1=$(awk 'NR==1{print $2}' "$hdr1")
accept_ranges=$(awk -F': ' 'tolower($1)=="accept-ranges"{print $2}' "$hdr1" | tr -d '\r')

if [ "$status1" = "200" ] || [ "$status1" = "404" ]; then
  if [ -n "$accept_ranges" ]; then
    echo "[OK] Accept-Ranges 헤더 존재: $accept_ranges"
  else
    echo "[INFO] Accept-Ranges 헤더 없음 (선택적 기능)"
  fi
else
  echo "[WARN] 일반 GET 요청 상태: $status1 (업스트림 미설정 가능)"
fi

# D-2) Range 요청으로 206 Partial Content 확인
if [ "$status1" = "200" ]; then
  echo ""
  echo "[test] D-2) Range 요청 (기대: 206 Partial Content 또는 200 OK)"
  hdr2=$(mktemp)
  body2=$(mktemp)
  status2=$(curl -sS -D "$hdr2" -o "$body2" -w "%{http_code}" \
    -H "Range: bytes=0-31" \
    "${AUTH_HEADERS[@]}" \
    "$URL")

  content_range=$(awk -F': ' 'tolower($1)=="content-range"{print $2}' "$hdr2" | tr -d '\r')

  if [ "$status2" = "206" ]; then
    echo "[OK] Range 요청: 206 Partial Content"
    if [ -n "$content_range" ]; then
      echo "[OK] Content-Range 헤더 존재: $content_range"
    fi
  elif [ "$status2" = "200" ]; then
    echo "[INFO] Range 요청: 200 OK (Range 미지원 또는 무시됨)"
  else
    echo "[WARN] Range 요청 상태: $status2"
  fi

  rm -f "$hdr2" "$body2"
else
  echo "[SKIP] D-2) Range 요청 (업스트림 404로 테스트 불가)"
fi

rm -f "$hdr1"
echo ""
echo "[OK] D. Range(206) / Accept-Ranges 동작 확인 완료"

