#!/usr/bin/env bash
set -euo pipefail

NO_NPM_INSTALL_FALLBACK_OK=0
cleanup(){ echo "NO_NPM_INSTALL_FALLBACK_OK=${NO_NPM_INSTALL_FALLBACK_OK}"; }
trap cleanup EXIT

# verify 스크립트에서 npm install(폴백) 금지: npm ci only 원칙 봉인
# rg 없거나 동작 안 하면 grep으로 폴백(설치 금지)
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
_filter() { grep -v '^[^:]*:[^:]*:#' | grep -v 'echo.*npm.*install' | grep -v 'verify_no_npm_install_fallback.sh' || true; }
if have_rg; then
  HITS="$(rg -n '\bnpm\s+install\b' scripts/verify webcore_appcore_starter_4_17/scripts/verify -g'*.sh' 2>/dev/null | _filter)"
else
  HITS="$(grep -RIn -E '\bnpm[[:space:]]+install\b' scripts/verify webcore_appcore_starter_4_17/scripts/verify --include='*.sh' 2>/dev/null | _filter)"
fi

if [[ -n "$HITS" ]]; then
  echo "FAIL: npm install fallback is forbidden in verify scripts (npm ci only)"
  echo "$HITS"
  exit 1
fi

NO_NPM_INSTALL_FALLBACK_OK=1
exit 0

