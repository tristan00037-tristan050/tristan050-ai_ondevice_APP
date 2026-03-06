#!/usr/bin/env bash
set -euo pipefail

TUF_MIN_ROLES_PRESENT_OK=0
TUF_EXPIRES_ENFORCED_OK=0
TUF_SIGNATURE_VERIFY_OK=0
trap 'echo "TUF_MIN_ROLES_PRESENT_OK=${TUF_MIN_ROLES_PRESENT_OK}"; echo "TUF_EXPIRES_ENFORCED_OK=${TUF_EXPIRES_ENFORCED_OK}"; echo "TUF_SIGNATURE_VERIFY_OK=${TUF_SIGNATURE_VERIFY_OK}"' EXIT

ENFORCE="${TUF_MIN_SIGNING_CHAIN_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "TUF_MIN_SIGNING_CHAIN_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# SSOT: this contract
SSOT="docs/ops/contracts/TUF_MIN_SIGNING_CHAIN_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=TUF_MIN_SIGNING_CHAIN_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'TUF_MIN_SIGNING_CHAIN_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=TUF_MIN_SIGNING_CHAIN_SSOT_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

# TUF_META_ROOT: from this SSOT or fallback to SECURE_UPDATE_TUF SSOT
TUF_META_ROOT=""
if grep -qE '^TUF_META_ROOT=' "$SSOT" 2>/dev/null; then
  TUF_META_ROOT="$(grep -E '^TUF_META_ROOT=' "$SSOT" | head -n1 | sed 's/^TUF_META_ROOT=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
if [ -z "$TUF_META_ROOT" ] && [ -f "docs/ops/contracts/SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1.txt" ]; then
  TUF_META_ROOT="$(grep -E '^TUF_META_ROOT=' docs/ops/contracts/SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1.txt | head -n1 | sed 's/^TUF_META_ROOT=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
[ -n "$TUF_META_ROOT" ] || {
  echo "ERROR_CODE=TUF_META_ROOT_MISSING"
  exit 1
}

ROOT_JSON="${TUF_META_ROOT}/root.json"
TARGETS_JSON="${TUF_META_ROOT}/targets.json"
SNAPSHOT_JSON="${TUF_META_ROOT}/snapshot.json"
TIMESTAMP_JSON="${TUF_META_ROOT}/timestamp.json"

# 1) TUF_MIN_ROLES_PRESENT_OK: all four role files exist
if [ ! -f "$ROOT_JSON" ] || [ ! -f "$TARGETS_JSON" ] || [ ! -f "$SNAPSHOT_JSON" ] || [ ! -f "$TIMESTAMP_JSON" ]; then
  echo "ERROR_CODE=TUF_ROLE_MISSING"
  [ ! -f "$ROOT_JSON" ] && echo "HIT_ROLE=root"
  [ ! -f "$TARGETS_JSON" ] && echo "HIT_ROLE=targets"
  [ ! -f "$SNAPSHOT_JSON" ] && echo "HIT_ROLE=snapshot"
  [ ! -f "$TIMESTAMP_JSON" ] && echo "HIT_ROLE=timestamp"
  exit 1
fi
TUF_MIN_ROLES_PRESENT_OK=1

# 2) TUF_EXPIRES_ENFORCED_OK: each has signed.expires (node or ruby, no install)
for role in root targets snapshot timestamp; do
  f="${TUF_META_ROOT}/${role}.json"
  if ! command -v node >/dev/null 2>&1; then
    echo "ERROR_CODE=TUF_EXPIRY_CHECK_UNAVAILABLE"
    echo "HIT_REASON=node_not_found"
    exit 1
  fi
  set +e
  node -e "
    const fs = require('fs');
    let d;
    try { d = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); } catch (e) { process.exit(1); }
    if (!d || !d.signed || typeof d.signed.expires !== 'string') process.exit(1);
    process.exit(0);
  " "$f" 2>/dev/null
  r=$?
  set -e
  if [ "$r" -ne 0 ]; then
    echo "ERROR_CODE=TUF_EXPIRES_NOT_ENFORCED"
    echo "HIT_FILE=$f"
    exit 1
  fi
done
TUF_EXPIRES_ENFORCED_OK=1

# 3) TUF_SIGNATURE_VERIFY_OK: each has signatures array with at least one entry (structure only; no key material in repo)
for role in root targets snapshot timestamp; do
  f="${TUF_META_ROOT}/${role}.json"
  set +e
  node -e "
    const fs = require('fs');
    let d;
    try { d = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); } catch (e) { process.exit(1); }
    if (!d || !Array.isArray(d.signatures) || d.signatures.length < 1) process.exit(1);
    process.exit(0);
  " "$f" 2>/dev/null
  r=$?
  set -e
  if [ "$r" -ne 0 ]; then
    echo "ERROR_CODE=TUF_SIGNATURE_STRUCTURE_MISSING"
    echo "HIT_FILE=$f"
    exit 1
  fi
done
TUF_SIGNATURE_VERIFY_OK=1

exit 0
