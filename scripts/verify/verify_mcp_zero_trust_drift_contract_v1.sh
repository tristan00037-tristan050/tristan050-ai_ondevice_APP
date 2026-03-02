#!/usr/bin/env bash
set -euo pipefail

MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=0
finish() { echo "MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=${MCP_ZERO_TRUST_DRIFT_CONTRACT_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

WATCHED=(
  "docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt"
  "tools/mcp_gateway/CAPABILITIES_DECLARED_V1.txt"
  "tools/mcp_gateway/enforcer_v1.cjs"
)
REQUIRED_GUARDS=(
  "mcp capabilities ssot v1"
  "mcp zero trust enforced v1"
)
CONTRACTS="scripts/verify/verify_repo_contracts.sh"

changed=0
diff_names="$(git diff --name-only origin/main...HEAD 2>/dev/null || true)"
for f in "${WATCHED[@]}"; do
  if echo "$diff_names" | grep -qF "$f"; then
    changed=1
    break
  fi
done

if [ "$changed" -eq 0 ]; then
  MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=1
  exit 0
fi

for g in "${REQUIRED_GUARDS[@]}"; do
  if ! grep -qF "run_guard \"${g}\"" "$CONTRACTS" 2>/dev/null; then
    echo "ERROR_CODE=MISSING_REQUIRED_GUARD"
    echo "MISSING_GUARD=${g}"
    exit 1
  fi
done

MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=1
exit 0
