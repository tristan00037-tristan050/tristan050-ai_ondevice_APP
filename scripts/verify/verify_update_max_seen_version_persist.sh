#!/usr/bin/env bash
set -euo pipefail

ANTI_ROLLBACK_PERSISTED_OK=0
MAX_SEEN_VERSION_MONOTONIC_OK=0
MAX_SEEN_VERSION_ATOMIC_UPDATE_OK=0
MAX_SEEN_VERSION_RESTART_SAFE_OK=0

cleanup(){
  echo "ANTI_ROLLBACK_PERSISTED_OK=${ANTI_ROLLBACK_PERSISTED_OK}"
  echo "MAX_SEEN_VERSION_MONOTONIC_OK=${MAX_SEEN_VERSION_MONOTONIC_OK}"
  echo "MAX_SEEN_VERSION_ATOMIC_UPDATE_OK=${MAX_SEEN_VERSION_ATOMIC_UPDATE_OK}"
  echo "MAX_SEEN_VERSION_RESTART_SAFE_OK=${MAX_SEEN_VERSION_RESTART_SAFE_OK}"
}
trap cleanup EXIT

TOP="$(git rev-parse --show-toplevel)"
DIR="${TOP}/webcore_appcore_starter_4_17/backend/model_registry"
cd "$DIR"

[[ -f package-lock.json ]] || { echo "FAIL: lockfile missing (package-lock.json): $DIR"; exit 1; }
# Check dependencies exist (workflow must install)
test -d "node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }

RESULT_JSON="/tmp/update_max_seen_version_persist.json"
rm -f "$RESULT_JSON"

set +e
npm test -- update_max_seen_version_persist.test.ts --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

[[ -f "$RESULT_JSON" ]] || { echo "FAIL: jest json output missing: $RESULT_JSON"; exit 1; }

node <<'NODE'
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/tmp/update_max_seen_version_persist.json','utf8'));

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

const need = ['ANTI_ROLLBACK_PERSISTED_OK','MAX_SEEN_VERSION_MONOTONIC_OK','MAX_SEEN_VERSION_ATOMIC_UPDATE_OK','MAX_SEEN_VERSION_RESTART_SAFE_OK'];
const allFound = need.every(x => evid.has(x));
const allPassed = (d.numFailedTests === 0) && (d.numPassedTests > 0);

process.exit((allFound && allPassed) ? 0 : 1);
NODE

PARSE_EXIT=$?

[[ "$TEST_EXIT" -eq 0 ]] || exit 1
[[ "$PARSE_EXIT" -eq 0 ]] || exit 1

ANTI_ROLLBACK_PERSISTED_OK=1
MAX_SEEN_VERSION_MONOTONIC_OK=1
MAX_SEEN_VERSION_ATOMIC_UPDATE_OK=1
MAX_SEEN_VERSION_RESTART_SAFE_OK=1
exit 0

