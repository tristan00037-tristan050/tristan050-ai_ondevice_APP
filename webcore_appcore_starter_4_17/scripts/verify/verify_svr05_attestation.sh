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

# Run tests and capture machine-verdict (Jest JSON), forbid log-grep based verdict
RESULT_JSON="/tmp/svr05_attestation_jest.json"
rm -f "$RESULT_JSON"

set +e
npm test -- --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

if [[ ! -f "$RESULT_JSON" ]]; then
  echo "FAIL: jest json output missing: $RESULT_JSON"
  exit 1
fi

# Parse Jest JSON to ensure:
# - attestation_http_e2e.test.ts ran and passed
# - at least one "denies request..." test passed
# - the "allows request..." test passed
node <<'NODE'
const fs = require('fs');
const p = "/tmp/svr05_attestation_jest.json";
const d = JSON.parse(fs.readFileSync(p, 'utf8'));

let allowOk = 0;
let denyOk = 0;

const tr = (d.testResults || []).find(x => String(x.name || '').includes('attestation_http_e2e.test.ts'));
if (!tr) process.exit(1);
if (String(tr.status) !== 'passed') process.exit(1);

for (const a of (tr.assertionResults || [])) {
  const title = String(a.title || '');
  const status = String(a.status || '');
  if (status !== 'passed') continue;
  if (title.startsWith('denies request')) denyOk = 1;
  if (title.startsWith('allows request')) allowOk = 1;
}

process.stdout.write(`ATTEST_ALLOW_OK=${allowOk}\n`);
process.stdout.write(`ATTEST_BLOCK_OK=${denyOk}\n`);
process.exit((allowOk && denyOk) ? 0 : 1);
NODE
PARSE_EXIT=$?

if [[ "$PARSE_EXIT" -ne 0 ]]; then
  exit 1
fi
if [[ "$TEST_EXIT" -ne 0 ]]; then
  exit 1
fi

# success keys
ATTEST_ALLOW_OK=1
ATTEST_BLOCK_OK=1
ATTEST_VERIFY_FAILCLOSED_OK=1
exit 0

