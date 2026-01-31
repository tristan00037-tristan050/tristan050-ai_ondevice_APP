#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

test -s "webcore_appcore_starter_4_17/scripts/web_e2e/p95_marks_server.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/p95_marks_page.html"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/p95_marks_page.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/run_p95_marks_e2e.mjs"
test -s "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_04_p95_marks_parity_e2e.sh"
test -s ".github/workflows/product-verify-web-ux-04.yml"

echo "OK"

