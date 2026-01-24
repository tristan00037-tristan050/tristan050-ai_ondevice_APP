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

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Jest 테스트를 통해 key rotation 검증 (이미 존재하는 테스트 활용)
cd "$ROOT/webcore_appcore_starter_4_17/backend/model_registry"

# 의존성 설치 확인
if [[ ! -d "node_modules" ]]; then
  npm ci
fi

# Jest 테스트 실행 및 JSON 결과 파싱
export RESULT_JSON="/tmp/key_rotation_test.json"
rm -f "$RESULT_JSON"

npm test -- keyops_rotation_revoke.test.ts --json --outputFile "$RESULT_JSON" 2>&1 | tail -20 || true

# JSON 결과 파싱하여 증거 키 확인
node <<'NODE'
const fs = require('fs');
const jsonPath = process.env.RESULT_JSON || '/tmp/key_rotation_test.json';
if (!fs.existsSync(jsonPath)) {
  console.error('FAIL: test json not found');
  process.exit(1);
}
const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

// 테스트 이름에서 EVID 태그 추출
const found = new Set();
function walk(node) {
  if (!node) return;
  if (typeof node === 'string') {
    const m = node.match(/\[EVID:([A-Z0-9_]+)\]/g);
    if (m) m.forEach(x => found.add(x.replace('[EVID:','').replace(']','')));
    return;
  }
  if (Array.isArray(node)) return node.forEach(walk);
  if (typeof node === 'object') {
    for (const k of Object.keys(node)) walk(node[k]);
  }
}
walk(data);

// 검증할 키
const requiredKeys = ['KEY_ROTATION_MULTIKEY_VERIFY_OK', 'KEY_ROTATION_GRACE_PERIOD_OK', 'KEY_REVOCATION_BLOCK_OK'];
const allFound = requiredKeys.every(k => found.has(k));
const allPassed = data.numFailedTests === 0 && data.numPassedTests > 0;

if (!allPassed || !allFound) {
  console.error('FAIL: key rotation tests failed or evidence keys missing');
  console.error('Found keys:', Array.from(found));
  console.error('Required keys:', requiredKeys);
  process.exit(1);
}
NODE

rc=$?
if [[ $rc -eq 0 ]]; then
  KEY_ROTATION_MULTIKEY_VERIFY_OK=1
  KEY_ROTATION_GRACE_PERIOD_OK=1
  KEY_REVOCATION_BLOCK_OK=1
  exit 0
fi

exit 1
