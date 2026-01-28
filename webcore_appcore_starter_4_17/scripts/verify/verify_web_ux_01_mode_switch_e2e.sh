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

test -s "${E2E_DIR}/package-lock.json" || { echo "BLOCK: package-lock.json missing (npm ci only)"; exit 1; }

npm --prefix "${E2E_DIR}" ci
npx --prefix "${E2E_DIR}" playwright install chromium

node "${E2E_DIR}/run_mode_switch_e2e.mjs"

WEB_E2E_MODE_SWITCH_WIRED_OK=1
WEB_E2E_MOCK_NETWORK_ZERO_OK=1
WEB_E2E_LIVE_HEADER_BUNDLE_OK=1
