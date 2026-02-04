#!/usr/bin/env bash
set -euo pipefail

WEB_META_ONLY_NEGATIVE_SUITE_OK=0

cleanup() {
  echo "WEB_META_ONLY_NEGATIVE_SUITE_OK=${WEB_META_ONLY_NEGATIVE_SUITE_OK}"
  if [[ "${WEB_META_ONLY_NEGATIVE_SUITE_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

node "${E2E_DIR}/run_meta_only_negative_e2e.mjs"

WEB_META_ONLY_NEGATIVE_SUITE_OK=1

