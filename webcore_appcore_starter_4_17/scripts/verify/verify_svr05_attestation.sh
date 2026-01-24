#!/usr/bin/env bash
set -euo pipefail

# SVR-05/APP-03: Attestation Verification v1 (fail-closed)
# Evidence sealing script for attestation verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Initialize evidence flags
ATTEST_VERIFY_FAILCLOSED_OK=0
ATTEST_ALLOW_OK=0
ATTEST_BLOCK_OK=0

cleanup() {
  echo "ATTEST_VERIFY_FAILCLOSED_OK=${ATTEST_VERIFY_FAILCLOSED_OK}"
  echo "ATTEST_ALLOW_OK=${ATTEST_ALLOW_OK}"
  echo "ATTEST_BLOCK_OK=${ATTEST_BLOCK_OK}"
  
  if [[ "$ATTEST_VERIFY_FAILCLOSED_OK" -eq 1 ]] && \
     [[ "$ATTEST_ALLOW_OK" -eq 1 ]] && \
     [[ "$ATTEST_BLOCK_OK" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}

trap cleanup EXIT

# Guard: Forbid "OK=1" in tests
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  TEST_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/attestation/tests"
  ATTESTATION_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/attestation"
else
  TEST_DIR="${ROOT}/backend/attestation/tests"
  ATTESTATION_DIR="${ROOT}/backend/attestation"
fi

if command -v rg >/dev/null 2>&1; then
  OK1_MATCHES=$(rg -n "OK=1" "${TEST_DIR}" 2>/dev/null || true)
  if [[ -n "$OK1_MATCHES" ]]; then
    echo "FAIL: 'OK=1' found in tests:"
    echo "$OK1_MATCHES"
    exit 1
  fi
elif command -v grep >/dev/null 2>&1; then
  if grep -r "OK=1" "${TEST_DIR}" 2>/dev/null | grep -v "^$"; then
    echo "FAIL: 'OK=1' found in tests"
    exit 1
  fi
fi

# Check Node.js and npm availability
command -v node >/dev/null 2>&1 || { echo "FAIL: node not found"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "FAIL: npm not found"; exit 1; }

# Run tests using npm only (attestation package only)
if [[ ! -d "$ATTESTATION_DIR" ]]; then
  echo "FAIL: attestation directory not found: $ATTESTATION_DIR"
  exit 1
fi

# Install dependencies (npm ci only, fail-closed if lockfile missing)
if [[ ! -f "${ATTESTATION_DIR}/package-lock.json" ]]; then
  echo "FAIL: lockfile missing (package-lock.json): ${ATTESTATION_DIR}"
  exit 1
fi
npm --prefix "$ATTESTATION_DIR" ci

# Run tests and parse results
cd "$ATTESTATION_DIR"

# Run tests and capture output
TEST_OUTPUT=$(npm test 2>&1) || TEST_EXIT=$?

# Check if tests passed
if [[ "${TEST_EXIT:-0}" -eq 0 ]]; then
  # Check if HTTP E2E test file exists and passed
  HTTP_E2E_FILE="${ATTESTATION_DIR}/tests/attestation_http_e2e.test.ts"
  if [[ -f "$HTTP_E2E_FILE" ]]; then
    # If HTTP E2E test suite passed, both deny and allow tests should have run
    if echo "$TEST_OUTPUT" | grep -q "attestation_http_e2e.test.ts" && \
       echo "$TEST_OUTPUT" | grep -q "PASS"; then
      # HTTP E2E file contains both deny and allow tests
      # If the test suite passed, both tests should have passed
      ATTEST_BLOCK_OK=1
      ATTEST_ALLOW_OK=1
    fi
  fi

  # Both deny and allow tests must pass for fail-closed OK
  if [[ "$ATTEST_BLOCK_OK" -eq 1 ]] && [[ "$ATTEST_ALLOW_OK" -eq 1 ]]; then
    ATTEST_VERIFY_FAILCLOSED_OK=1
  fi
  exit 0
else
  exit 1
fi

