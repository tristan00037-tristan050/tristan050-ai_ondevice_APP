#!/usr/bin/env bash
set -euo pipefail

# Telemetry E2E Verification (fail-closed)
# Evidence sealing script for telemetry meta-only schema guard and ingest verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Initialize evidence flags
TELEM_META_ONLY_SCHEMA_GUARD_OK=0
TELEM_REJECT_RAW_OK=0
TELEM_INGEST_OK=0

cleanup() {
  echo "TELEM_META_ONLY_SCHEMA_GUARD_OK=${TELEM_META_ONLY_SCHEMA_GUARD_OK}"
  echo "TELEM_REJECT_RAW_OK=${TELEM_REJECT_RAW_OK}"
  echo "TELEM_INGEST_OK=${TELEM_INGEST_OK}"
  
  if [[ "$TELEM_META_ONLY_SCHEMA_GUARD_OK" -eq 1 ]] && \
     [[ "$TELEM_REJECT_RAW_OK" -eq 1 ]] && \
     [[ "$TELEM_INGEST_OK" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}

trap cleanup EXIT

# Guard: Forbid "OK=1" in tests (only check telemetry_e2e.test.ts)
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  TEST_FILE="${ROOT}/webcore_appcore_starter_4_17/backend/telemetry/tests/telemetry_e2e.test.ts"
  TELEMETRY_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/telemetry"
else
  TEST_FILE="${ROOT}/backend/telemetry/tests/telemetry_e2e.test.ts"
  TELEMETRY_DIR="${ROOT}/backend/telemetry"
fi

if command -v rg >/dev/null 2>&1; then
  OK1_MATCHES=$(rg -n "OK=1" "${TEST_FILE}" 2>/dev/null || true)
  if [[ -n "$OK1_MATCHES" ]]; then
    echo "FAIL: 'OK=1' found in tests:"
    echo "$OK1_MATCHES"
    exit 1
  fi
elif command -v grep >/dev/null 2>&1; then
  if grep -r "OK=1" "${TEST_FILE}" 2>/dev/null | grep -v "^$"; then
    echo "FAIL: 'OK=1' found in tests"
    exit 1
  fi
fi

# Check Node.js and npm availability
command -v node >/dev/null 2>&1 || { echo "FAIL: node not found"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "FAIL: npm not found"; exit 1; }

# Run tests using npm only (telemetry package only)
if [[ ! -d "$TELEMETRY_DIR" ]]; then
  echo "FAIL: telemetry directory not found: $TELEMETRY_DIR"
  exit 1
fi

# Install dependencies
# First install control_plane dependencies (telemetry depends on it)
CONTROL_PLANE_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/control_plane"
if [[ -d "$CONTROL_PLANE_DIR" ]]; then
  if [[ -f "${CONTROL_PLANE_DIR}/package-lock.json" ]]; then
    npm --prefix "$CONTROL_PLANE_DIR" ci
  else
    npm --prefix "$CONTROL_PLANE_DIR" install
  fi
fi

# Then install telemetry dependencies
if [[ -f "${TELEMETRY_DIR}/package-lock.json" ]]; then
  npm --prefix "$TELEMETRY_DIR" ci
else
  npm --prefix "$TELEMETRY_DIR" install
fi

# Run tests
if npm --prefix "$TELEMETRY_DIR" test; then
  TELEM_META_ONLY_SCHEMA_GUARD_OK=1
  TELEM_REJECT_RAW_OK=1
  TELEM_INGEST_OK=1
  exit 0
else
  exit 1
fi

