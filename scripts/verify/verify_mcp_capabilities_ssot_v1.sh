#!/usr/bin/env bash
set -euo pipefail

MCP_CAPABILITIES_SSOT_V1_OK=0
finish() { echo "MCP_CAPABILITIES_SSOT_V1_OK=${MCP_CAPABILITIES_SSOT_V1_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt"
test -f "$SSOT" || { echo "ERROR_CODE=MCP_SSOT_MISSING"; exit 1; }
grep -q '^MCP_CAPABILITIES_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=MCP_SSOT_TOKEN_MISSING"; exit 1; }

MCP_CAPABILITIES_SSOT_V1_OK=1
exit 0
