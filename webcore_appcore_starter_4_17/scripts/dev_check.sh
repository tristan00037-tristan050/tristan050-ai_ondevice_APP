#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://localhost:8081}"
WEB_ORIGIN="${WEB_ORIGIN:-http://localhost:8083}"

echo "[check] 1) healthz"
curl -fsS -i "${BFF}/healthz" | sed -n '1,12p'
echo

echo "[check] 2) CORS preflight reflect (OPTIONS /v1/os/llm-usage)"
curl -fsS -i -X OPTIONS \
  -H "Origin: ${WEB_ORIGIN}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-tenant,x-user-id,x-user-role,x-api-key" \
  "${BFF}/v1/os/llm-usage" | sed -n '1,30p'
echo

echo "[check] 3) POST /v1/os/llm-usage (meta-only, 204)"
curl -fsS -i -X POST \
  -H "Content-Type: application/json" \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "${BFF}/v1/os/llm-usage" \
  -d '{"eventType":"cs_hud_demo","suggestionLength":0}' | sed -n '1,20p'
echo

echo "[check] 4) CS tickets 200 OK"
curl -fsS -i \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "${BFF}/v1/cs/tickets?limit=1&offset=0" | sed -n '1,40p'
echo

# --- [check] 5) Model artifact proxy security + caching (E06-2B/E06-3) ---
MODEL_ID="${WEBLLM_TEST_MODEL_ID:-}"
MODEL_FILE="${WEBLLM_TEST_MODEL_FILE:-}"   # 예: manifest.json (작은 json 권장)

if [ -n "$MODEL_ID" ] && [ -n "$MODEL_FILE" ]; then
  URL="${BFF}/v1/os/models/${MODEL_ID}/${MODEL_FILE}"

  echo "[check] 5-1) Model proxy headers (HEAD): ${URL}"
  HEADERS="$(curl -sSI \
    -H "X-Tenant: default" \
    -H "X-User-Id: hud-user-1" \
    -H "X-User-Role: operator" \
    -H "X-Api-Key: collector-key:operator" \
    "${URL}")"

  CODE="$(echo "$HEADERS" | head -n 1 | awk '{print $2}')"
  echo "$HEADERS" | sed -n '1,40p'

  if [ "$CODE" != "200" ] && [ "$CODE" != "304" ]; then
    echo "[check] FAIL: HEAD returned ${CODE}. Showing response body:"
    curl -i \
      -H "X-Tenant: default" \
      -H "X-User-Id: hud-user-1" \
      -H "X-User-Role: operator" \
      -H "X-Api-Key: collector-key:operator" \
      "${URL}" | sed -n '1,120p'
    exit 1
  fi

  ETAG="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')"
  CC="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="cache-control"{print $2}' | tr -d '\r')"
  CL="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="content-length"{print $2}' | tr -d '\r')"
  AR="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="accept-ranges"{print $2}' | tr -d '\r')"

  if [ -z "$ETAG" ]; then echo "[check] FAIL: ETag missing"; exit 1; fi
  if [ -z "$CC" ]; then echo "[check] FAIL: Cache-Control missing"; exit 1; fi
  if [ -z "$CL" ]; then echo "[check] FAIL: Content-Length missing"; exit 1; fi
  
  # Accept-Ranges 헤더 확인 (대용량 파일 Range 요청 지원 여부)
  if [ -z "$AR" ]; then
    echo "[check] WARN: Accept-Ranges header missing (Range requests may not be supported)"
  else
    echo "[check] OK: Accept-Ranges=${AR}"
  fi

  echo "[check] 5-2) 304 Not Modified check (If-None-Match)"
  CODE_304="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "If-None-Match: ${ETAG}" \
    -H "X-Tenant: default" \
    -H "X-User-Id: hud-user-1" \
    -H "X-User-Role: operator" \
    -H "X-Api-Key: collector-key:operator" \
    "${URL}")"
  if [ "$CODE_304" != "304" ] && [ "$CODE_304" != "200" ]; then
    echo "[check] FAIL: unexpected status for If-None-Match: ${CODE_304}"
    exit 1
  fi

  # Range 요청 테스트 (대용량 파일 지원 확인)
  if [ -n "$AR" ] && [ "$AR" != "none" ]; then
    echo "[check] 5-2b) Range request check (bytes=0-99)"
    RANGE_HEADERS="$(curl -sSI \
      -H "Range: bytes=0-99" \
      -H "X-Tenant: default" \
      -H "X-User-Id: hud-user-1" \
      -H "X-User-Role: operator" \
      -H "X-Api-Key: collector-key:operator" \
      "${URL}")"
    RANGE_CODE="$(echo "$RANGE_HEADERS" | head -n 1 | awk '{print $2}')"
    CR="$(echo "$RANGE_HEADERS" | awk -F': ' 'tolower($1)=="content-range"{print $2}' | tr -d '\r')"
    
    if [ "$RANGE_CODE" = "206" ]; then
      if [ -n "$CR" ]; then
        echo "[check] OK: Range request returned 206 with Content-Range=${CR}"
      else
        echo "[check] WARN: Range request returned 206 but Content-Range missing"
      fi
    elif [ "$RANGE_CODE" = "200" ]; then
      echo "[check] WARN: Range request returned 200 (full response, Range may not be supported)"
    else
      echo "[check] WARN: Range request returned ${RANGE_CODE} (unexpected)"
    fi
  fi

  echo "[check] 5-3) Proxy security negative tests"

  CODE_FORBIDDEN="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "X-Tenant: default" \
    -H "X-User-Id: hud-user-1" \
    -H "X-User-Role: operator" \
    -H "X-Api-Key: collector-key:operator" \
    "${BFF}/v1/os/models/__not_allowed__/manifest.json")"
  if [ "$CODE_FORBIDDEN" != "403" ]; then
    echo "[check] FAIL: expected 403 for not-allowed modelId, got ${CODE_FORBIDDEN}"
    exit 1
  fi

  CODE_BAD_EXT="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "X-Tenant: default" \
    -H "X-User-Id: hud-user-1" \
    -H "X-User-Role: operator" \
    -H "X-Api-Key: collector-key:operator" \
    "${BFF}/v1/os/models/${MODEL_ID}/evil.exe")"
  if [ "$CODE_BAD_EXT" != "400" ]; then
    echo "[check] FAIL: expected 400 for disallowed extension, got ${CODE_BAD_EXT}"
    exit 1
  fi

  echo "[check] 5) Model proxy checks OK"
else
  echo "[check] 5) Model proxy checks SKIP (set WEBLLM_TEST_MODEL_ID and WEBLLM_TEST_MODEL_FILE)"
  echo "        e.g. WEBLLM_TEST_MODEL_ID=local-llm-v1 WEBLLM_TEST_MODEL_FILE=manifest.json"
fi

echo
echo "[check] DONE"
