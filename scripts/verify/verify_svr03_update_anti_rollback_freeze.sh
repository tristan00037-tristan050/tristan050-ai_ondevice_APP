#!/usr/bin/env bash
set -euo pipefail

ANTI_ROLLBACK_ENFORCED_OK=0
ANTI_FREEZE_EXPIRES_ENFORCED_OK=0
ANTI_ROLLBACK_WIRED_OK=0

cleanup(){
  echo "ANTI_ROLLBACK_ENFORCED_OK=${ANTI_ROLLBACK_ENFORCED_OK}"
  echo "ANTI_FREEZE_EXPIRES_ENFORCED_OK=${ANTI_FREEZE_EXPIRES_ENFORCED_OK}"
  echo "ANTI_ROLLBACK_WIRED_OK=${ANTI_ROLLBACK_WIRED_OK}"
}
trap cleanup EXIT

TOP="$(git rev-parse --show-toplevel)"
DIR="${TOP}/webcore_appcore_starter_4_17/backend/model_registry"
cd "$DIR"

[[ -f package-lock.json ]] || { echo "FAIL: lockfile missing (package-lock.json): $DIR"; exit 1; }
# Check dependencies exist (workflow must install)
test -d "node_modules" || { echo "BLOCK: node_modules missing (workflow must run dependency install)"; exit 1; }

# 정적 스캔: signature.ts에 함수가 실제로 연결되어야 함 (rg 없거나 동작 안 하면 grep 폴백)
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
if have_rg; then
  rg -n "enforceAntiRollbackFreeze" verify/signature.ts >/dev/null || { echo "FAIL: not wired in verify/signature.ts"; exit 1; }
else
  grep -n "enforceAntiRollbackFreeze" verify/signature.ts >/dev/null || { echo "FAIL: not wired in verify/signature.ts"; exit 1; }
fi
ANTI_ROLLBACK_WIRED_OK=1

RESULT_JSON="/tmp/svr03_update_anti_rollback_freeze.json"
rm -f "$RESULT_JSON"

set +e
npm test -- update_anti_rollback_freeze_contract.test.ts --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

[[ -f "$RESULT_JSON" ]] || { echo "FAIL: jest json output missing: $RESULT_JSON"; exit 1; }

node <<'NODE'
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/tmp/svr03_update_anti_rollback_freeze.json','utf8'));

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

const need = ['ANTI_ROLLBACK_ENFORCED_OK','ANTI_FREEZE_EXPIRES_ENFORCED_OK'];
const allFound = need.every(x => evid.has(x));
const allPassed = (d.numFailedTests === 0) && (d.numPassedTests > 0);

process.exit((allFound && allPassed) ? 0 : 1);
NODE

PARSE_EXIT=$?

[[ "$TEST_EXIT" -eq 0 ]] || exit 1
[[ "$PARSE_EXIT" -eq 0 ]] || exit 1

ANTI_ROLLBACK_ENFORCED_OK=1
ANTI_FREEZE_EXPIRES_ENFORCED_OK=1
exit 0

