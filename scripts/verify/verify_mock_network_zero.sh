#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/MOCK_NETWORK_ZERO_SSOT.json"
[ -f "$SSOT" ] || { echo "MOCK_NETWORK_ZERO_OK=0"; exit 1; }

[ -f "webcore_appcore_starter_4_17/backend/gateway/mw/mock_network_zero_gate.ts" ] || { echo "MOCK_NETWORK_ZERO_OK=0"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
run_n() { if have_rg; then rg -n "$1" "$2" -S >/dev/null 2>&1; else grep -nE "$1" "$2" >/dev/null 2>&1; fi; }

run_n "forbidMockModeNetwork" webcore_appcore_starter_4_17/backend/telemetry/index.ts || { echo "MOCK_NETWORK_ZERO_OK=0"; exit 1; }

run_n "\\[EVID:MOCK_NETWORK_ZERO_OK\\]" webcore_appcore_starter_4_17/backend/telemetry/tests/mock_network_zero_gate.test.ts || { echo "MOCK_NETWORK_ZERO_OK=0"; exit 1; }

echo "MOCK_NETWORK_ZERO_OK=1"

