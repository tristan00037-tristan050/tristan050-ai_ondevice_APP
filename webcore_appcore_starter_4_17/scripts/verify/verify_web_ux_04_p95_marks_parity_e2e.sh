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

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

node "${E2E_DIR}/run_p95_marks_e2e.mjs"

PERF_E2E_EVENT_MARKS_WIRED_OK=1
PERF_E2E_MARKS_PARITY_OK=1

