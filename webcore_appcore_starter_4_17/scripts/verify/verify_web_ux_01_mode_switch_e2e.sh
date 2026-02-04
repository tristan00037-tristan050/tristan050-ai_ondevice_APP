#!/usr/bin/env bash
set -euo pipefail

WEB_E2E_MODE_SWITCH_WIRED_OK=0
WEB_E2E_MOCK_NETWORK_ZERO_OK=0
WEB_E2E_LIVE_HEADER_BUNDLE_OK=0

cleanup() {
  echo "WEB_E2E_MODE_SWITCH_WIRED_OK=${WEB_E2E_MODE_SWITCH_WIRED_OK}"
  echo "WEB_E2E_MOCK_NETWORK_ZERO_OK=${WEB_E2E_MOCK_NETWORK_ZERO_OK}"
  echo "WEB_E2E_LIVE_HEADER_BUNDLE_OK=${WEB_E2E_LIVE_HEADER_BUNDLE_OK}"
}
trap cleanup EXIT

E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

node "${E2E_DIR}/run_mode_switch_e2e.mjs"

WEB_E2E_MODE_SWITCH_WIRED_OK=1
WEB_E2E_MOCK_NETWORK_ZERO_OK=1
WEB_E2E_LIVE_HEADER_BUNDLE_OK=1
