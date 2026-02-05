#!/usr/bin/env bash
set -euo pipefail

# Web Console Verification Gate (fail-closed)
# Evidence sealing script for web console verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  ROOT="${ROOT}/webcore_appcore_starter_4_17"
fi
cd "$ROOT"

# Initialize evidence flags
CONSOLE_ONBOARDING_DONE_OK=0
RBAC_UI_ENFORCE_OK=0

cleanup() {
  echo "CONSOLE_ONBOARDING_DONE_OK=${CONSOLE_ONBOARDING_DONE_OK}"
  echo "RBAC_UI_ENFORCE_OK=${RBAC_UI_ENFORCE_OK}"
  
  if [[ "$CONSOLE_ONBOARDING_DONE_OK" -eq 1 ]] && \
     [[ "$RBAC_UI_ENFORCE_OK" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}

trap cleanup EXIT

# Guard: Forbid "OK=1" in tests (admin/tests only)
WEB_CONSOLE_ADMIN_TESTS_DIR="${ROOT}/web_console/admin/tests"

if command -v rg >/dev/null 2>&1; then
  OK1_MATCHES=$(rg -n "OK=1" "${WEB_CONSOLE_ADMIN_TESTS_DIR}" 2>/dev/null || true)
  if [[ -n "$OK1_MATCHES" ]]; then
    echo "FAIL: 'OK=1' found in web_console/admin/tests:"
    echo "$OK1_MATCHES"
    exit 1
  fi
elif command -v grep >/dev/null 2>&1; then
  if grep -r "OK=1" "${WEB_CONSOLE_ADMIN_TESTS_DIR}" 2>/dev/null | grep -v "^$"; then
    echo "FAIL: 'OK=1' found in web_console/admin/tests"
    exit 1
  fi
fi

# Check Node.js and npm availability
command -v node >/dev/null 2>&1 || { echo "FAIL: node not found"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "FAIL: npm not found"; exit 1; }

# Run tests using npm only (ops-console package)
OPS_CONSOLE_DIR="${ROOT}/packages/ops-console"
WEB_CONSOLE_ADMIN_DIR="${ROOT}/web_console/admin"

# Check if directories exist
if [[ ! -d "$OPS_CONSOLE_DIR" ]]; then
  echo "FAIL: ops-console directory not found: $OPS_CONSOLE_DIR"
  exit 1
fi

if [[ ! -d "$WEB_CONSOLE_ADMIN_DIR" ]]; then
  echo "FAIL: web_console/admin directory not found: $WEB_CONSOLE_ADMIN_DIR"
  exit 1
fi

# Guard: package-lock.json required (fail-closed)
LOCK="${OPS_CONSOLE_DIR}/package-lock.json"
if [[ ! -f "$LOCK" ]]; then
  echo "FAIL: package-lock.json required: $LOCK"
  echo "This ensures deterministic, reproducible builds in CI"
  exit 1
fi

# Check dependencies exist (workflow must install)
test -d "${OPS_CONSOLE_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }

# Check jest binary exists (workflow must install)
JEST_BIN="${OPS_CONSOLE_DIR}/node_modules/.bin/jest"
test -f "$JEST_BIN" || { echo "BLOCK: jest binary missing (workflow must run npm ci in ops-console)"; exit 1; }

# Run tests using npm-only (ops-console's jest)
# Tests are in web_console/admin/tests
cd "${WEB_CONSOLE_ADMIN_DIR}"

# Use jest from ops-console node_modules
# Set NODE_PATH to include ops-console node_modules for ts-jest
export NODE_PATH="${OPS_CONSOLE_DIR}/node_modules:${NODE_PATH:-}"

# Run tests using jest with config (npm-only, no ts-node/tsx)
if "$JEST_BIN" -c jest.config.cjs tests/integration.test.ts tests/e2e.test.ts tests/rbac_ui.test.tsx --no-coverage 2>&1; then
  CONSOLE_ONBOARDING_DONE_OK=1
  RBAC_UI_ENFORCE_OK=1
  exit 0
else
  exit 1
fi

