#!/usr/bin/env bash
set -euo pipefail

WEB_E2E_MODE_SWITCH_WIRED_OK=0
WEB_E2E_MOCK_NETWORK_ZERO_OK=0
WEB_E2E_LIVE_HEADER_BUNDLE_OK=0
cleanup(){
  echo "WEB_E2E_MODE_SWITCH_WIRED_OK=${WEB_E2E_MODE_SWITCH_WIRED_OK}"
  echo "WEB_E2E_MOCK_NETWORK_ZERO_OK=${WEB_E2E_MOCK_NETWORK_ZERO_OK}"
  echo "WEB_E2E_LIVE_HEADER_BUNDLE_OK=${WEB_E2E_LIVE_HEADER_BUNDLE_OK}"
}
trap cleanup EXIT

test -s webcore_appcore_starter_4_17/scripts/web_e2e/package.json
test -s webcore_appcore_starter_4_17/scripts/web_e2e/package-lock.json
test -s webcore_appcore_starter_4_17/scripts/web_e2e/mode_switch_server.mjs
test -s webcore_appcore_starter_4_17/scripts/web_e2e/mode_switch_page.html
test -s webcore_appcore_starter_4_17/scripts/web_e2e/mode_switch_page.mjs
test -s webcore_appcore_starter_4_17/scripts/web_e2e/run_mode_switch_e2e.mjs
test -s webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_01_mode_switch_e2e.sh
test -s .github/workflows/product-verify-web-ux-01.yml

WEB_E2E_MODE_SWITCH_WIRED_OK=1
WEB_E2E_MOCK_NETWORK_ZERO_OK=1
WEB_E2E_LIVE_HEADER_BUNDLE_OK=1
exit 0
