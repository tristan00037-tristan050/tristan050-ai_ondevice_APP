#!/usr/bin/env bash
set -euo pipefail

KEY_ROTATION_MULTIKEY_VERIFY_OK=0
KEY_ROTATION_GRACE_PERIOD_OK=0
KEY_REVOCATION_BLOCK_OK=0

cleanup() {
  echo "KEY_ROTATION_MULTIKEY_VERIFY_OK=${KEY_ROTATION_MULTIKEY_VERIFY_OK}"
  echo "KEY_ROTATION_GRACE_PERIOD_OK=${KEY_ROTATION_GRACE_PERIOD_OK}"
  echo "KEY_REVOCATION_BLOCK_OK=${KEY_REVOCATION_BLOCK_OK}"
}
trap cleanup EXIT

TOP="$(git rev-parse --show-toplevel)"
DIR="${TOP}/webcore_appcore_starter_4_17/backend/model_registry"
cd "$DIR"

# npm ci only + lockfile required
[[ -f package-lock.json ]] || { echo "FAIL: lockfile missing (package-lock.json): $DIR"; exit 1; }
npm ci

RESULT_JSON="/tmp/svr03_key_rotation_revoke.json"
rm -f "$RESULT_JSON"

set +e
npm test -- keyops_rotation_revoke.test.ts --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

[[ -f "$RESULT_JSON" ]] || { echo "FAIL: jest json output missing: $RESULT_JSON"; exit 1; }

node <<'NODE'
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/tmp/svr03_key_rotation_revoke.json','utf8'));

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

const need = [
  'KEY_ROTATION_MULTIKEY_VERIFY_OK',
  'KEY_ROTATION_GRACE_PERIOD_OK',
  'KEY_REVOCATION_BLOCK_OK'
];

const allFound = need.every(x => evid.has(x));
const allPassed = (d.numFailedTests === 0) && (d.numPassedTests > 0);

process.exit((allFound && allPassed) ? 0 : 1);
NODE
PARSE_EXIT=$?

[[ "$TEST_EXIT" -eq 0 ]] || exit 1
[[ "$PARSE_EXIT" -eq 0 ]] || exit 1

KEY_ROTATION_MULTIKEY_VERIFY_OK=1
KEY_ROTATION_GRACE_PERIOD_OK=1
KEY_REVOCATION_BLOCK_OK=1
exit 0
