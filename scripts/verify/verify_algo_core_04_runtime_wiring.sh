#!/usr/bin/env bash
set -euo pipefail

# fast asset gate (CI friendly)
BFF_INDEX="webcore_appcore_starter_4_17/packages/bff-accounting/src/index.ts"
ROUTE="webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/os-algo-core.ts"
LIB="webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts"

test -s "$BFF_INDEX"
test -s "$ROUTE"
test -s "$LIB"

# must be mounted
grep -nF -- 'app.use("/v1/os/algo", osAlgoCoreRouter);' "$BFF_INDEX" >/dev/null

# must enforce fail-closed prod keys (static presence of env check)
grep -nF -- 'ALGO_CORE_PROD_KEYS_REQUIRED_FAILCLOSED' "$LIB" >/dev/null
grep -nF -- 'ALGO_CORE_PROD_KEY_ID_NOT_ALLOWED_FAILCLOSED' "$LIB" >/dev/null

echo "ALGO_CORE_RUNTIME_ROUTE_PRESENT_OK=1"
echo "ALGO_CORE_RUNTIME_PROD_FAILCLOSED_KEYS_OK=1"
exit 0

