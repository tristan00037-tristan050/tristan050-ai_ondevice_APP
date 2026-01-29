#!/usr/bin/env bash
set -euo pipefail

RUNTIME_V0_HTTP_OK=0
RUNTIME_EGRESS_DENY_DEFAULT_OK=0

cleanup(){
  echo "RUNTIME_V0_HTTP_OK=${RUNTIME_V0_HTTP_OK}"
  echo "RUNTIME_EGRESS_DENY_DEFAULT_OK=${RUNTIME_EGRESS_DENY_DEFAULT_OK}"
  if [[ "${RUNTIME_V0_HTTP_OK}" == "1" ]] && [[ "${RUNTIME_EGRESS_DENY_DEFAULT_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PKG="webcore_appcore_starter_4_17/packages/butler-runtime"
test -s "$PKG/package.json"
test -s "$PKG/src/server.mjs"
test -s "$PKG/src/safe_net.mjs"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

PORT=8091
export RUNTIME_PORT="$PORT"

# start server
node "$PKG/src/server.mjs" --smoke >/tmp/runtime_v0.out 2>&1 &
PID=$!

# wait
for i in $(seq 1 50); do
  if grep -q "RUNTIME_LISTENING=1" /tmp/runtime_v0.out; then break; fi
  sleep 0.1
done

# HTTP check
BODY="$(curl -sS -X POST "http://127.0.0.1:${PORT}/v1/runtime/three-blocks" \
  -H "Content-Type: application/json" \
  --data '{"request_id":"req1","dept":"acct","tier":"S","signals":{"x":1}}')"

echo "$BODY" | node -e '
const s=require("fs").readFileSync(0,"utf8"); const o=JSON.parse(s);
if(o.ok!==true) process.exit(1);
if(!o.blocks || Object.keys(o.blocks).length!==3) process.exit(1);
process.exit(0);
' >/dev/null
RUNTIME_V0_HTTP_OK=1

# Egress deny default check: calling assertInternalUrlOrThrow must throw
node - <<'NODE'
import { assertInternalUrlOrThrow } from "./webcore_appcore_starter_4_17/packages/butler-runtime/src/safe_net.mjs";
try {
  assertInternalUrlOrThrow("https://example.com");
  process.exit(1);
} catch (e) {
  if (String(e?.message||"").includes("RUNTIME_EGRESS_DENY_DEFAULT_FAILCLOSED")) process.exit(0);
  process.exit(1);
}
NODE
RUNTIME_EGRESS_DENY_DEFAULT_OK=1

kill "$PID" >/dev/null 2>&1 || true
exit 0
