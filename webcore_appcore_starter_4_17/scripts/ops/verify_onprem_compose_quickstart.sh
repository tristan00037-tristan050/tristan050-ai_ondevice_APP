#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

BFF_URL="${BFF_URL:-http://127.0.0.1:8081}"

fail(){ echo "FAIL: $*"; exit 1; }

echo "== onprem compose: up (build) =="
docker compose up -d --build

cleanup(){
  echo "== onprem compose: down =="
  docker compose down -v || true
}
trap cleanup EXIT

echo "== wait healthz/readyz =="
for i in $(seq 1 40); do
  if curl -fsS --max-time 2 "$BFF_URL/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  [ "$i" -eq 40 ] && fail "healthz not ready"
done

curl -fsS --max-time 2 "$BFF_URL/healthz" >/dev/null || fail "healthz fail"
curl -fsS --max-time 3 "$BFF_URL/readyz" >/dev/null || fail "readyz fail"

echo "ONPREM_COMPOSE_UP_OK=1"
echo "HEALTHZ_GATEWAY_OK=1"
echo "READYZ_GATEWAY_OK=1"

echo "== build anchor verify (output-based) =="
BASE_URL="$BFF_URL" bash scripts/ops/verify_build_anchor.sh
echo "BUILD_ANCHOR_OK=1"

echo "OK: onprem compose quickstart smoke PASS"

