#!/usr/bin/env bash
set -euo pipefail

NO_NPM_INSTALL_FALLBACK_OK=0
cleanup(){ echo "NO_NPM_INSTALL_FALLBACK_OK=${NO_NPM_INSTALL_FALLBACK_OK}"; }
trap cleanup EXIT

command -v rg >/dev/null 2>&1 || { echo "FAIL: rg not found"; exit 1; }

# verify 스크립트에서 npm install(폴백) 금지: npm ci only 원칙 봉인
# 실제 명령어 실행만 검사 (주석/echo 제외)
HITS="$(rg -n '\bnpm\s+install\b' \
  scripts/verify \
  webcore_appcore_starter_4_17/scripts/verify \
  -g'*.sh' 2>/dev/null | \
  grep -v '^[^:]*:[^:]*:#' | \
  grep -v 'echo.*npm.*install' | \
  grep -v 'verify_no_npm_install_fallback.sh' || true)"

if [[ -n "$HITS" ]]; then
  echo "FAIL: npm install fallback is forbidden in verify scripts (npm ci only)"
  echo "$HITS"
  exit 1
fi

NO_NPM_INSTALL_FALLBACK_OK=1
exit 0

