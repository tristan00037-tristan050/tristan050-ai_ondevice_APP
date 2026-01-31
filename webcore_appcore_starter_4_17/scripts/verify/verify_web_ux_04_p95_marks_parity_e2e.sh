#!/usr/bin/env bash
set -euo pipefail

PERF_E2E_EVENT_MARKS_WIRED_OK=0
PERF_E2E_MARKS_PARITY_OK=0

cleanup() {
  echo "PERF_E2E_EVENT_MARKS_WIRED_OK=${PERF_E2E_EVENT_MARKS_WIRED_OK}"
  echo "PERF_E2E_MARKS_PARITY_OK=${PERF_E2E_MARKS_PARITY_OK}"
}
trap cleanup EXIT

E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"
test -s "${E2E_DIR}/package-lock.json" || { echo "BLOCK: package-lock.json missing (npm ci only)"; exit 1; }

npm --prefix "${E2E_DIR}" ci
npx --prefix "${E2E_DIR}" playwright install chromium

node "${E2E_DIR}/run_p95_marks_e2e.mjs"

PERF_E2E_EVENT_MARKS_WIRED_OK=1
PERF_E2E_MARKS_PARITY_OK=1

