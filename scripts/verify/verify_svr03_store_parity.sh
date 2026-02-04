#!/usr/bin/env bash
set -euo pipefail

STORE_CONTRACT_TESTS_SHARED_OK=0
DBSTORE_PARITY_SMOKE_OK=0
DBSTORE_REAL_ADAPTER_PARITY_OK=0
DBSTORE_CONCURRENCY_OK=0
DBSTORE_NO_PARTIAL_WRITE_OK=0

cleanup(){
  echo "STORE_CONTRACT_TESTS_SHARED_OK=${STORE_CONTRACT_TESTS_SHARED_OK}"
  echo "DBSTORE_PARITY_SMOKE_OK=${DBSTORE_PARITY_SMOKE_OK}"
  echo "DBSTORE_REAL_ADAPTER_PARITY_OK=${DBSTORE_REAL_ADAPTER_PARITY_OK}"
  echo "DBSTORE_CONCURRENCY_OK=${DBSTORE_CONCURRENCY_OK}"
  echo "DBSTORE_NO_PARTIAL_WRITE_OK=${DBSTORE_NO_PARTIAL_WRITE_OK}"
}
trap cleanup EXIT

TOP="$(git rev-parse --show-toplevel)"
DIR="${TOP}/webcore_appcore_starter_4_17/backend/model_registry"
cd "$DIR"

[[ -f package-lock.json ]] || { echo "FAIL: lockfile missing (package-lock.json): $DIR"; exit 1; }
# Check dependencies exist (workflow must install)
test -d "node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }

RESULT_JSON="/tmp/svr03_store_parity.json"
rm -f "$RESULT_JSON"

set +e
npm test -- store_contract_parity.test.ts dbstore_real_adapter.test.ts --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

[[ -f "$RESULT_JSON" ]] || { echo "FAIL: jest json output missing: $RESULT_JSON"; exit 1; }

node <<'NODE'
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/tmp/svr03_store_parity.json','utf8'));

function collectEvid(node, out){
  if (node == null) return;
  if (typeof node === 'string'){
    const ms = node.match(/\[EVID:([A-Z0-9_]+)\]/g) || [];
    for (const m of ms) out.add(m.slice(6, -1));
    return;
  }
  if (Array.isArray(node)) return node.forEach(x => collectEvid(x, out));
  if (typeof node === 'object') for (const k of Object.keys(node)) collectEvid(node[k], out);
}

const evid = new Set();
collectEvid(d, evid);

// STORE-02: expanded evidence keys
const need = [
  'STORE_CONTRACT_TESTS_SHARED_OK',
  'DBSTORE_PARITY_SMOKE_OK',
  'DBSTORE_REAL_ADAPTER_PARITY_OK',
  'DBSTORE_CONCURRENCY_OK',
  'DBSTORE_NO_PARTIAL_WRITE_OK'
];
const allFound = need.every(x => evid.has(x));
const allPassed = (d.numFailedTests === 0) && (d.numPassedTests > 0);

process.exit((allFound && allPassed) ? 0 : 1);
NODE

PARSE_EXIT=$?

[[ "$TEST_EXIT" -eq 0 ]] || exit 1
[[ "$PARSE_EXIT" -eq 0 ]] || exit 1

STORE_CONTRACT_TESTS_SHARED_OK=1
DBSTORE_PARITY_SMOKE_OK=1
DBSTORE_REAL_ADAPTER_PARITY_OK=1
DBSTORE_CONCURRENCY_OK=1
DBSTORE_NO_PARTIAL_WRITE_OK=1
exit 0

