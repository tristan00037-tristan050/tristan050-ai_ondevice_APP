#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://localhost:8081}"
WEB_ORIGIN="${WEB_ORIGIN:-http://localhost:8083}"

# Team standard v1 (with safe defaults for local)
WEBLLM_TEST_MODEL_ID="${WEBLLM_TEST_MODEL_ID:-local-llm-v1}"
WEBLLM_TEST_MODEL_FILE="${WEBLLM_TEST_MODEL_FILE:-manifest.json}"

hdr() {
  echo "------------------------------------------------------------"
  echo "$1"
  echo "------------------------------------------------------------"
}

need_header() {
  local file="$1"
  local key="$2"
  if ! grep -i -q "^${key}:" "$file"; then
    echo "[FAIL] missing header: ${key}"
    echo "== headers =="
    cat "$file"
    exit 1
  fi
}

get_header_val() {
  local file="$1"
  local key="$2"
  grep -i "^${key}:" "$file" | head -n1 | sed -E "s/^${key}:\s*//I" | tr -d '\r'
}

req_headers=(
  -H "X-Tenant: default"
  -H "X-User-Id: hud-user-1"
  -H "X-User-Role: operator"
  -H "X-Api-Key: collector-key:operator"
)

# temp files
H1="$(mktemp)"; B1="$(mktemp)"
H2="$(mktemp)"; B2="$(mktemp)"
trap 'rm -f "$H1" "$B1" "$H2" "$B2"' EXIT

hdr "[check] 1) healthz"
curl -fsS -D "$H1" -o "$B1" "${BFF}/healthz" >/dev/null
status="$(awk 'NR==1{print $2}' "$H1")"
[ "$status" = "200" ] || { echo "[FAIL] healthz status=$status"; cat "$H1"; exit 1; }
echo "[OK] healthz 200"

hdr "[check] 2) CORS preflight (OPTIONS /v1/os/llm-usage)"
curl -fsS -D "$H1" -o /dev/null -X OPTIONS \
  -H "Origin: ${WEB_ORIGIN}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-tenant,x-user-id,x-user-role,x-api-key,idempotency-key" \
  "${BFF}/v1/os/llm-usage" >/dev/null
status="$(awk 'NR==1{print $2}' "$H1")"
[ "$status" = "204" ] || { echo "[FAIL] preflight status=$status"; cat "$H1"; exit 1; }
echo "[OK] preflight 204"

hdr "[check] 3) POST /v1/os/llm-usage (meta-only -> 204)"
curl -fsS -D "$H1" -o /dev/null -X POST \
  -H "Content-Type: application/json" \
  "${req_headers[@]}" \
  "${BFF}/v1/os/llm-usage" \
  -d '{"eventType":"qa_trigger_llm_usage","suggestionLength":0}' >/dev/null
status="$(awk 'NR==1{print $2}' "$H1")"
[ "$status" = "204" ] || { echo "[FAIL] llm-usage status=$status"; cat "$H1"; exit 1; }
echo "[OK] llm-usage 204 (meta-only)"

hdr "[check] 4) CS tickets 200"
curl -fsS -D "$H1" -o "$B1" \
  "${req_headers[@]}" \
  "${BFF}/v1/cs/tickets?limit=1&offset=0" >/dev/null
status="$(awk 'NR==1{print $2}' "$H1")"
[ "$status" = "200" ] || { echo "[FAIL] cs tickets status=$status"; cat "$H1"; exit 1; }
echo "[OK] cs tickets 200"

hdr "[check] 5) model proxy headers + cache + 304 (ETag/Cache-Control/Content-Length/If-None-Match)"
URL="${BFF}/v1/os/models/${WEBLLM_TEST_MODEL_ID}/${WEBLLM_TEST_MODEL_FILE}"

# 5-1) 200 + headers
curl -fsS -D "$H1" -o "$B1" \
  "${req_headers[@]}" \
  "$URL" >/dev/null

status="$(awk 'NR==1{print $2}' "$H1")"
[ "$status" = "200" ] || { echo "[FAIL] model proxy status=$status"; cat "$H1"; exit 1; }

need_header "$H1" "etag"
need_header "$H1" "cache-control"
need_header "$H1" "content-length"

ETAG="$(get_header_val "$H1" "etag")"
CC="$(get_header_val "$H1" "cache-control")"
CL="$(get_header_val "$H1" "content-length")"

# Cache-Control: public, max-age=86400 포함 여부
echo "$CC" | grep -qi "public" || { echo "[FAIL] cache-control missing 'public': $CC"; exit 1; }
echo "$CC" | grep -qi "max-age=86400" || { echo "[FAIL] cache-control missing 'max-age=86400': $CC"; exit 1; }

# Content-Length numeric
echo "$CL" | grep -Eqi '^[0-9]+$' || { echo "[FAIL] content-length not numeric: $CL"; exit 1; }

echo "[OK] model proxy 200 + headers (ETag/Cache-Control/Content-Length)"

# 5-2) 304
curl -fsS -D "$H2" -o /dev/null \
  -H "If-None-Match: ${ETAG}" \
  "${req_headers[@]}" \
  "$URL" >/dev/null

status2="$(awk 'NR==1{print $2}' "$H2")"
[ "$status2" = "304" ] || { echo "[FAIL] If-None-Match expected 304, got $status2"; cat "$H2"; exit 1; }
echo "[OK] model proxy 304 (If-None-Match)"

hdr "[check] 6) model proxy negative tests (403/400)"

# 6-1) unknown modelId -> 403
BAD_URL="${BFF}/v1/os/models/__no_such_model__/${WEBLLM_TEST_MODEL_FILE}"
curl -sS -D "$H1" -o /dev/null \
  "${req_headers[@]}" \
  "$BAD_URL" >/dev/null || true
s="$(awk 'NR==1{print $2}' "$H1")"
[ "$s" = "403" ] || { echo "[FAIL] expected 403 for unknown modelId, got $s"; cat "$H1"; exit 1; }
echo "[OK] unknown modelId -> 403"

# 6-2) traversal -> 400
TRAV_URL="${BFF}/v1/os/models/${WEBLLM_TEST_MODEL_ID}/..%2F..%2Fetc%2Fpasswd"
curl -sS -D "$H1" -o /dev/null \
  "${req_headers[@]}" \
  "$TRAV_URL" >/dev/null || true
s="$(awk 'NR==1{print $2}' "$H1")"
[ "$s" = "400" ] || { echo "[FAIL] expected 400 for traversal, got $s"; cat "$H1"; exit 1; }
echo "[OK] traversal blocked -> 400"

# 6-3) bad extension -> 400
BAD_EXT_URL="${BFF}/v1/os/models/${WEBLLM_TEST_MODEL_ID}/malware.exe"
curl -sS -D "$H1" -o /dev/null \
  "${req_headers[@]}" \
  "$BAD_EXT_URL" >/dev/null || true
s="$(awk 'NR==1{print $2}' "$H1")"
[ "$s" = "400" ] || { echo "[FAIL] expected 400 for bad extension, got $s"; cat "$H1"; exit 1; }
echo "[OK] extension allowlist -> 400"

echo
echo "PASS"
echo "dev_check: healthz 200 / preflight 204 / llm-usage 204(meta-only) / cs tickets 200 / model proxy headers+cache+negative tests OK (ETag, Cache-Control, Content-Length, If-None-Match)"
