#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

test -s "webcore_appcore_starter_4_17/scripts/web_e2e/meta_only_negative_server.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/meta_only_negative_page.html"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/meta_only_negative_page.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/run_meta_only_negative_e2e.mjs"
test -s "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_08_meta_only_negative_suite.sh"
test -s ".github/workflows/product-verify-web-ux-08.yml"

echo "OK"

