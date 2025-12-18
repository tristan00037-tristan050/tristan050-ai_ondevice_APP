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

echo "[check] DONE"
