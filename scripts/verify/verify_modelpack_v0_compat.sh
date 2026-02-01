#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=0
MODEL_PACK_V0_COMPAT_ENFORCED_OK=0

cleanup() {
  echo "MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=${MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK}"
  echo "MODEL_PACK_V0_COMPAT_ENFORCED_OK=${MODEL_PACK_V0_COMPAT_ENFORCED_OK}"
  if [[ "${MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_V0_COMPAT_ENFORCED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 1) 실제 팩(accounting_v0)에 compat 필수
GOOD="model_packs/accounting_v0/pack.json"
test -s "$GOOD" || { echo "BLOCK: missing $GOOD"; exit 1; }

COMPAT="$(jq -r '.compat' "$GOOD" 2>/dev/null || echo "null")"
if [[ "$COMPAT" == "null" || "$COMPAT" == "" ]]; then
  echo "FAIL: compat missing in $GOOD"
  exit 1
fi

MIN_RUNTIME="$(jq -r '.compat.min_runtime_semver' "$GOOD" 2>/dev/null || echo "")"
MIN_GATEWAY="$(jq -r '.compat.min_gateway_semver' "$GOOD" 2>/dev/null || echo "")"

if [[ -z "$MIN_RUNTIME" || -z "$MIN_GATEWAY" ]]; then
  echo "FAIL: compat fields missing in $GOOD"
  exit 1
fi

# 2) strict X.Y.Z 형식 검증
if ! node -e "
  const s = process.argv[1];
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(s.trim());
  if (!m) process.exit(1);
  const [major, minor, patch] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (![major, minor, patch].every(Number.isInteger)) process.exit(1);
" "$MIN_RUNTIME"; then
  echo "FAIL: min_runtime_semver not strict X.Y.Z: $MIN_RUNTIME"
  exit 1
fi

if ! node -e "
  const s = process.argv[1];
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(s.trim());
  if (!m) process.exit(1);
  const [major, minor, patch] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (![major, minor, patch].every(Number.isInteger)) process.exit(1);
" "$MIN_GATEWAY"; then
  echo "FAIL: min_gateway_semver not strict X.Y.Z: $MIN_GATEWAY"
  exit 1
fi

MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=1

# 3) 실패 fixture 존재 확인
BAD_RUNTIME="model_packs/_bad_compat_runtime_too_low/pack.json"
BAD_GATEWAY="model_packs/_bad_compat_gateway_too_low/pack.json"

test -s "$BAD_RUNTIME" || { echo "BLOCK: missing $BAD_RUNTIME"; exit 1; }
test -s "$BAD_GATEWAY" || { echo "BLOCK: missing $BAD_GATEWAY"; exit 1; }

MODEL_PACK_V0_COMPAT_ENFORCED_OK=1
exit 0

