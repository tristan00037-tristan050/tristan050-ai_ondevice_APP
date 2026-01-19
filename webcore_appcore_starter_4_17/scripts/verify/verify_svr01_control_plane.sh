#!/bin/bash
# verify_svr01_control_plane.sh
# Output-based DoD verification for SVR-01 Control Plane
# Emits *_OK keys only on success (exit 0)

set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel)"
cd "${TOPLEVEL}/webcore_appcore_starter_4_17/backend/control_plane"

# Guard: Fail if any OK=1 pattern exists in tests
echo "Checking for OK=1 patterns in tests..."
if command -v rg >/dev/null 2>&1; then
  if rg -n "OK=1" tests/ 2>/dev/null | grep -v "^$" > /dev/null; then
    echo "FAIL: Found OK=1 pattern in test files"
    rg -n "OK=1" tests/ 2>/dev/null || true
    exit 1
  fi
else
  # Fallback to grep if ripgrep is not available
  if grep -rn "OK=1" tests/ 2>/dev/null | grep -v "^$" > /dev/null; then
    echo "FAIL: Found OK=1 pattern in test files"
    grep -rn "OK=1" tests/ 2>/dev/null || true
    exit 1
  fi
fi

# Initialize OK flags
TENANT_LIST_SCOPED_OK=0
TENANT_LIST_ALL_REQUIRES_SUPERADMIN_OK=0
AUDIT_DENY_COVERAGE_OK=0
RBAC_DEFAULT_DENY_OK=0
SVR01_SEALED_OK=0

# Install dependencies (fail-closed)
echo "Installing dependencies..."
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

# Run tests
echo "Running tests..."
if npm test 2>&1; then
  TEST_RC=0
else
  TEST_RC=$?
fi

# Determine OK flags based on test results
if [ "${TEST_RC}" -eq 0 ]; then
  # All tests passed
  TENANT_LIST_SCOPED_OK=1
  TENANT_LIST_ALL_REQUIRES_SUPERADMIN_OK=1
  AUDIT_DENY_COVERAGE_OK=1
  RBAC_DEFAULT_DENY_OK=1
  SVR01_SEALED_OK=1
else
  # Tests failed
  echo "FAIL: Tests failed with exit code ${TEST_RC}"
fi

# Emit OK keys
echo "TENANT_LIST_SCOPED_OK=${TENANT_LIST_SCOPED_OK}"
echo "TENANT_LIST_ALL_REQUIRES_SUPERADMIN_OK=${TENANT_LIST_ALL_REQUIRES_SUPERADMIN_OK}"
echo "AUDIT_DENY_COVERAGE_OK=${AUDIT_DENY_COVERAGE_OK}"
echo "RBAC_DEFAULT_DENY_OK=${RBAC_DEFAULT_DENY_OK}"
echo "SVR01_SEALED_OK=${SVR01_SEALED_OK}"

# Exit with appropriate code
if [ "${SVR01_SEALED_OK}" -eq 1 ]; then
  exit 0
else
  exit 1
fi

