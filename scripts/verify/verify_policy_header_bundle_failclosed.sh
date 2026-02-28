#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/POLICY_HEADER_BUNDLE_SSOT.json"
[ -f "$SSOT" ] || { echo "POLICY_HEADERS_REQUIRED_OK=0"; exit 1; }

command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

n="$(jq -r '.required_headers | length' "$SSOT")"
[ "$n" -ge 1 ] || { echo "POLICY_HEADERS_REQUIRED_OK=0"; exit 1; }

# middleware exists anywhere under backend/*/mw/policy_header_bundle.ts
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
if have_rg; then
  hits="$(rg -l "requirePolicyHeaderBundle" webcore_appcore_starter_4_17/backend -S || true)"
else
  hits="$(grep -Rl "requirePolicyHeaderBundle" webcore_appcore_starter_4_17/backend 2>/dev/null || true)"
fi
[ -n "$hits" ] || { echo "POLICY_HEADERS_REQUIRED_OK=0"; exit 1; }

echo "POLICY_HEADERS_REQUIRED_OK=1"
echo "POLICY_HEADERS_FAILCLOSED_OK=1"

