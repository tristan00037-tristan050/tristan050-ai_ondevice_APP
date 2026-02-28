#!/usr/bin/env bash
set -euo pipefail

# Hardening++ 3.2: skipped/neutral 우회 차단(정적 검사)
# job/step에서 continue-on-error, if: always()로 중립화하거나,
# 결과가 neutral/skipped로 빠질 수 있는 패턴을 금지한다.

REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=0
cleanup(){ echo "REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=${REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK}"; }
trap cleanup EXIT

WF_DIR=".github/workflows"
[[ -d "$WF_DIR" ]] || { echo "FAIL: missing $WF_DIR"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

if have_rg; then
  HITS="$(rg -n --no-messages \
    -e 'continue-on-error:\s*true' \
    -e 'if:\s*always\(\)' \
    -e 'if:\s*success\(\)\s*\|\|\s*failure\(\)' \
    "$WF_DIR"/product-verify-*.yml "$WF_DIR"/product-verify-*.yaml 2>/dev/null || true)"
else
  # grep fallback
  PAT='(continue-on-error:\s*true|if:\s*always\(\)|if:\s*success\(\)\s*\|\|\s*failure\(\))'
  HITS="$(grep -RIn \
    --exclude-dir=node_modules \
    -E "$PAT" \
    "$WF_DIR"/product-verify-*.yml "$WF_DIR"/product-verify-*.yaml 2>/dev/null || true)"
fi

if [[ -n "$HITS" ]]; then
  echo "FAIL: skipped/neutral bypass patterns found in product-verify workflows"
  echo "$HITS"
  exit 1
fi

REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=1
exit 0

