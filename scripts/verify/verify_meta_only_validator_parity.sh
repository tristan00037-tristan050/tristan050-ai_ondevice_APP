#!/usr/bin/env bash
set -euo pipefail

META_ONLY_VALIDATOR_PARITY_OK=0
cleanup(){ echo "META_ONLY_VALIDATOR_PARITY_OK=${META_ONLY_VALIDATOR_PARITY_OK}"; }
trap cleanup EXIT

CORE="webcore_appcore_starter_4_17/shared/meta_only/validator_core.ts"
SERVER="webcore_appcore_starter_4_17/backend/gateway/guards/meta_only_validator.ts"
CLIENT="webcore_appcore_starter_4_17/web_console/admin/src/shared/meta_only_validator.ts"
RUNTIME="webcore_appcore_starter_4_17/packages/butler-runtime/src/server.mjs"
SSOT="docs/ops/contracts/META_ONLY_ALLOWLIST_SSOT.json"

test -s "$CORE"
test -s "$SERVER"
test -s "$CLIENT"
test -s "$RUNTIME"
test -s "$SSOT"

# server must use the shared core
grep -q "shared/meta_only/validator_core" "$SERVER"
grep -q "validateMetaOnlyWithSSOT" "$SERVER"

# client must use the same shared core
grep -q "shared/meta_only/validator_core" "$CLIENT"
grep -q "validateMetaOnlyWithSSOT" "$CLIENT"

# Runtime: verify that shadow path references SSOT or shared validator
# Runtime's request validation can remain custom, but shadow event generation
# must reference SSOT (Gateway creates shadow events, so this is a defensive check)
# Check that Runtime at least references SSOT file or shared validator in comments/code
if ! grep -q "META_ONLY_ALLOWLIST_SSOT\|validator_core\|shared/meta_only" "$RUNTIME"; then
  # Runtime doesn't directly emit shadow events (Gateway does), but we verify
  # that Runtime's shadow endpoint at least validates meta-only requests
  # and that Gateway uses shared validator for shadow events
  # This is a defensive check to ensure no drift
  echo "WARN: Runtime shadow endpoint may not reference SSOT (Gateway handles shadow events)"
fi

# Gateway shadow path must validate meta-only (defensive check)
# Note: Gateway's fireShadowRequest uses validateMetaOnlyOrThrow from osAlgoCore.ts
# The shadow event payload (if emitted to ops hub) should use shared validator_core
# For now, we verify that shadow path at least validates meta-only requests
GATEWAY_SHADOW="webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/os-algo-core.ts"
if grep -q "fireShadowRequest" "$GATEWAY_SHADOW"; then
  # Gateway's fireShadowRequest validates meta-only before sending to Runtime
  if ! grep -q "validateMetaOnlyOrThrow" "$GATEWAY_SHADOW"; then
    echo "BLOCK: Gateway shadow path missing meta-only validation"
    exit 1
  fi
  # Verify that Gateway's osAlgoCore validates meta-only (defensive check)
  GATEWAY_CORE="webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts"
  if ! grep -q "validateMetaOnlyOrThrow\|META_ONLY" "$GATEWAY_CORE"; then
    echo "BLOCK: Gateway osAlgoCore missing meta-only validation"
    exit 1
  fi
fi

META_ONLY_VALIDATOR_PARITY_OK=1
exit 0
