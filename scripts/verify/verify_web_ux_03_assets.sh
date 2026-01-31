#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 파일 존재(자산)만 확인: repo-guards는 무거운 실행 대신 자산 봉인
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/export_audit_server.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/export_audit_page.html"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/export_audit_page.mjs"
test -s "webcore_appcore_starter_4_17/scripts/web_e2e/run_export_audit_e2e.mjs"
test -s "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_03_export_auditv2_e2e.sh"
test -s ".github/workflows/product-verify-web-ux-03.yml"

echo "OK"

