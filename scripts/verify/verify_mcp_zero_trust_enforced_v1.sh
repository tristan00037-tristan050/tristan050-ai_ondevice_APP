#!/usr/bin/env bash
set -euo pipefail

MCP_ZERO_TRUST_ENFORCED_OK=0
finish() { echo "MCP_ZERO_TRUST_ENFORCED_OK=${MCP_ZERO_TRUST_ENFORCED_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

ENFORCER="tools/mcp_gateway/enforcer_v1.cjs"
test -f "$ENFORCER" || { echo "ERROR_CODE=MCP_ENFORCER_MISSING"; exit 1; }

export GIT_ROOT="$ROOT"
node "$ENFORCER" || { echo "ERROR_CODE=MCP_ZERO_TRUST_CHECK_FAILED"; exit 1; }

MCP_ZERO_TRUST_ENFORCED_OK=1
exit 0
