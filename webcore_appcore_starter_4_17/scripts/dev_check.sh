#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://localhost:8081}"
WEB_ORIGIN="${WEB_ORIGIN:-http://localhost:8083}"

echo "[check] 1) healthz"
curl -fsS -i "${BFF}/healthz" | sed -n '1,10p'
echo

echo "[check] 2) CORS preflight reflect (OPTIONS /v1/os/llm-usage)"
curl -fsS -i -X OPTIONS \
  -H "Origin: ${WEB_ORIGIN}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-tenant,x-user-id,x-user-role,x-api-key" \
  "${BFF}/v1/os/llm-usage" | sed -n '1,30p'
echo

echo "[check] 3) POST /v1/os/llm-usage (eventType + suggestionLength, 원문 0)"
curl -fsS -i -X POST \
  -H "Content-Type: application/json" \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "${BFF}/v1/os/llm-usage" \
  -d '{"domain":"cs_hud","engineId":"local-rule-v1","engineMode":"rule","engineStub":true,"eventType":"cs_hud_demo","feature":"qa_trigger_from_app","timestamp":"2025-12-17T00:00:00.000Z","suggestionLength":0}' \
  | sed -n '1,20p'
echo

echo "[check] 4) CS tickets 200 OK"
curl -fsS -i \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "${BFF}/v1/cs/tickets?limit=1&offset=0" | sed -n '1,30p'
echo
# --- [check] 5) Model artifact proxy security + caching (E06-2B/E06-3) ---

MODEL_ID="${WEBLLM_TEST_MODEL_ID:-}"
MODEL_FILE="${WEBLLM_TEST_MODEL_FILE:-}"   # 예: manifest.json 또는 실제 존재하는 파일(권장: 작은 json)

if [ -n "$MODEL_ID" ] && [ -n "$MODEL_FILE" ]; then
  URL="${BFF}/v1/os/models/${MODEL_ID}/${MODEL_FILE}"

  echo "[check] 5-1) Model proxy headers (HEAD): ${URL}"
  HEADERS="$(curl -fsSI \
    -H "X-Tenant: default" \
    -H "X-User-Id: hud-user-1" \
    -H "X-User-Role: operator" \
    -H "X-Api-Key: collector-key:operator" \
    "${URL}")"

  echo "$HEADERS" | sed -n '1,40p'
  ETAG="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')"
  CC="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="cache-control"{print $2}' | tr -d '\r')"
  CL="$(echo "$HEADERS" | awk -F': ' 'tolower($1)=="content-length"{print $2}' | tr -d '\r')"

  if [ -z "$ETAG" ]; then
    echo "[check] FAIL: ETag missing"
    exit 1
  fi
  if [ -z "$CC" ]; then
    echo "[check] FAIL: Cache-Control missing"
    exit 1
  fi
  if [ -z "$CL" ]; then
    echo "[check] FAIL: Content-Length missing"
    exit 1
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
echo "[check] DONE"
