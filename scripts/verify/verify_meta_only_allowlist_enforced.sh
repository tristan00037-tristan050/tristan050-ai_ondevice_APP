#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/META_ONLY_ALLOWLIST_SSOT.json"
[ -f "$SSOT" ] || { echo "META_ONLY_ALLOWLIST_ENFORCED_OK=0"; exit 1; }

command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

n="$(jq -r '.allowed_keys | length' "$SSOT")"
[ "$n" -ge 1 ] || { echo "META_ONLY_ALLOWLIST_ENFORCED_OK=0"; exit 1; }

# Validator + middleware must exist
[ -f "webcore_appcore_starter_4_17/backend/gateway/guards/meta_only_validator.ts" ] || { echo "META_ONLY_ALLOWLIST_ENFORCED_OK=0"; exit 1; }
[ -f "webcore_appcore_starter_4_17/backend/gateway/mw/meta_only_gate.ts" ] || { echo "META_ONLY_ALLOWLIST_ENFORCED_OK=0"; exit 1; }

echo "META_ONLY_ALLOWLIST_ENFORCED_OK=1"

