#!/usr/bin/env bash
set -euo pipefail

MCP_ZERO_TRUST_ENFORCED_OK=0
finish() { echo "MCP_ZERO_TRUST_ENFORCED_OK=${MCP_ZERO_TRUST_ENFORCED_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt"
DECLARED="tools/mcp_gateway/CAPABILITIES_DECLARED_V1.txt"
ENFORCER="tools/mcp_gateway/enforcer_v1.cjs"

test -f "$SSOT" || { echo "ERROR_CODE=MCP_SSOT_MISSING"; exit 1; }
grep -q '^MCP_CAPABILITIES_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=MCP_SSOT_TOKEN_MISSING"; exit 1; }
test -f "$DECLARED" || { echo "ERROR_CODE=MCP_DECLARED_MISSING"; exit 1; }
grep -q '^MCP_GATEWAY_CAPABILITIES_DECLARED_V1_TOKEN=1' "$DECLARED" || { echo "ERROR_CODE=MCP_DECLARED_TOKEN_MISSING"; exit 1; }
test -f "$ENFORCER" || { echo "ERROR_CODE=MCP_ENFORCER_MISSING"; exit 1; }

export GIT_ROOT="$ROOT"
node "$ENFORCER" --ssot "$SSOT" --declared "$DECLARED" || { echo "ERROR_CODE=MCP_ZERO_TRUST_CHECK_FAILED"; exit 1; }

MCP_ZERO_TRUST_ENFORCED_OK=1
exit 0
