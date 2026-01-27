#!/usr/bin/env bash
set -euo pipefail

META_ONLY_VALIDATOR_PARITY_OK=0
cleanup(){ echo "META_ONLY_VALIDATOR_PARITY_OK=${META_ONLY_VALIDATOR_PARITY_OK}"; }
trap cleanup EXIT

CORE="webcore_appcore_starter_4_17/shared/meta_only/validator_core.ts"
SERVER="webcore_appcore_starter_4_17/backend/gateway/guards/meta_only_validator.ts"
CLIENT="webcore_appcore_starter_4_17/web_console/admin/src/shared/meta_only_validator.ts"

test -s "$CORE"
test -s "$SERVER"
test -s "$CLIENT"

# server must use the shared core
grep -q "shared/meta_only/validator_core" "$SERVER"
grep -q "validateMetaOnlyWithSSOT" "$SERVER"

# client must use the same shared core
grep -q "shared/meta_only/validator_core" "$CLIENT"
grep -q "validateMetaOnlyWithSSOT" "$CLIENT"

META_ONLY_VALIDATOR_PARITY_OK=1
exit 0
