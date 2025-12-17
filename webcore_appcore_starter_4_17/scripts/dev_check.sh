#!/usr/bin/env bash
set -euo pipefail

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[dev_check] healthz"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -sS -i http://localhost:8081/healthz | sed -n '1,12p'

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[dev_check] CS tickets (should be 200)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -sS -i \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "http://localhost:8081/v1/cs/tickets?limit=1&offset=0" | sed -n '1,25p'

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[dev_check] os llm-usage (should be 204)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -sS -i -X POST \
  -H "Content-Type: application/json" \
  -H "X-Tenant: default" \
  -H "X-User-Id: hud-user-1" \
  -H "X-User-Role: operator" \
  -H "X-Api-Key: collector-key:operator" \
  "http://localhost:8081/v1/os/llm-usage" \
  -d '{"eventType":"cs_hud_demo","suggestionLength":0}' | sed -n '1,20p'

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[dev_check] CORS preflight (accounting approvals w/ idempotency-key)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -sS -i -X OPTIONS "http://127.0.0.1:8081/v1/accounting/approvals/sample-id" \
  -H "Origin: http://localhost:8083" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-tenant,x-user-id,x-user-role,x-api-key,idempotency-key" \
  | sed -n '1,30p'

