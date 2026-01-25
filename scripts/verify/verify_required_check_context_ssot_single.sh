#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/REQUIRED_CHECK_CONTEXTS_SSOT.json"
[ -f "$SSOT" ] || { echo "BLOCK: missing SSOT: $SSOT"; exit 1; }

command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

count="$(jq -r '.required_checks.supplychain | length' "$SSOT")"
[ "$count" = "1" ] || { echo "BLOCK: supplychain contexts must be 1, got=$count"; echo "REQUIRED_CHECK_CONTEXT_SINGLE_OK=0"; exit 1; }

name="$(jq -r '.required_checks.supplychain[0]' "$SSOT")"
[ "$name" = "product-verify-supplychain" ] || { echo "BLOCK: unexpected context: $name"; echo "REQUIRED_CHECK_CONTEXT_SINGLE_OK=0"; exit 1; }

echo "OK: SUPPLYCHAIN_REQUIRED_CHECK_CONTEXT=$name"
echo "REQUIRED_CHECK_CONTEXT_SINGLE_OK=1"
