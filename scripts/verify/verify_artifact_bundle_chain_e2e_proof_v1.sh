#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_CHAIN_E2E_POLICY_V1_OK=0
ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PRESENT_OK=0
ARTIFACT_BUNDLE_CHAIN_E2E_META_ONLY_OK=0
trap 'echo "ARTIFACT_BUNDLE_CHAIN_E2E_POLICY_V1_OK=${ARTIFACT_BUNDLE_CHAIN_E2E_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PRESENT_OK=${ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PRESENT_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_E2E_META_ONLY_OK=${ARTIFACT_BUNDLE_CHAIN_E2E_META_ONLY_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

# proof 경로: SSOT 또는 기본값. proof/latest 면 해당 경로 또는 proof/latest.json
PROOF_PATH=""
if grep -qE '^ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PATH=' "$SSOT" 2>/dev/null; then
  PROOF_PATH="$(grep -E '^ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PATH=' "$SSOT" | head -n1 | sed 's/^ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
[ -n "$PROOF_PATH" ] || PROOF_PATH="docs/ops/proofs/artifact_bundle_chain_e2e_latest.json"

# proof/latest 디렉터리면 그 안의 latest 파일 사용
if [ -d "$PROOF_PATH" ]; then
  if [ -f "${PROOF_PATH}/latest.json" ]; then
    PROOF_PATH="${PROOF_PATH}/latest.json"
  elif [ -f "${PROOF_PATH}/latest" ]; then
    PROOF_PATH="${PROOF_PATH}/latest"
  else
    echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_MISSING"
    echo "HIT_PATH=$PROOF_PATH"
    exit 1
  fi
fi

if [ ! -f "$PROOF_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_MISSING"
  echo "HIT_PATH=$PROOF_PATH"
  exit 1
fi
ARTIFACT_BUNDLE_CHAIN_E2E_PROOF_PRESENT_OK=1

command -v node >/dev/null 2>&1 || {
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_INVALID"
  exit 1
}

# JSON 유효성 + meta-only 검사 (원문/긴 덤프 금지)
set +e
node -e "
const fs = require('fs');
const proofPath = process.argv[1];
const MAX_VAL_LEN = 500;
const FORBIDDEN_KEYS = ['raw', 'origin', 'content', 'body', 'full_output', 'stdout', 'stderr'];
let o;
try {
  o = JSON.parse(fs.readFileSync(proofPath, 'utf8'));
} catch (e) { process.exit(10); }
if (!o || typeof o !== 'object') process.exit(10);
function checkMetaOnly(obj, depth) {
  if (depth > 5) process.exit(12);
  for (const k of Object.keys(obj)) {
    if (FORBIDDEN_KEYS.includes(k)) process.exit(12);
    const v = obj[k];
    if (typeof v === 'string' && v.length > MAX_VAL_LEN) process.exit(12);
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) checkMetaOnly(v, depth + 1);
    if (Array.isArray(v)) { for (const item of v) { if (typeof item === 'object' && item !== null) checkMetaOnly(item, depth + 1); } }
  }
}
checkMetaOnly(o, 0);
process.exit(0);
" "$PROOF_PATH" 2>/dev/null
rc=$?
set -e
if [ "$rc" -eq 10 ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_INVALID"
  echo "HIT_PATH=$PROOF_PATH"
  exit 1
fi
if [ "$rc" -eq 12 ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_META_ONLY_VIOLATION"
  echo "HIT_PATH=$PROOF_PATH"
  exit 1
fi
if [ "$rc" -ne 0 ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_E2E_PROOF_INVALID"
  echo "HIT_PATH=$PROOF_PATH"
  exit 1
fi

ARTIFACT_BUNDLE_CHAIN_E2E_META_ONLY_OK=1
ARTIFACT_BUNDLE_CHAIN_E2E_POLICY_V1_OK=1
exit 0
