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
test -s "${E2E_DIR}/package-lock.json" || { echo "BLOCK: package-lock.json missing (npm ci only)"; exit 1; }

npm --prefix "${E2E_DIR}" ci
npx --prefix "${E2E_DIR}" playwright install chromium

node "${E2E_DIR}/run_meta_only_negative_e2e.mjs"

WEB_META_ONLY_NEGATIVE_SUITE_OK=1

