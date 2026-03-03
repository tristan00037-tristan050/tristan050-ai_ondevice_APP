#!/usr/bin/env bash
set -euo pipefail

SECURE_UPDATE_TUF_PRINCIPLES_V1_OK=0
finish() { [ "${SECURE_UPDATE_TUF_PRINCIPLES_V1_OK:-0}" -eq 1 ] && echo "SECURE_UPDATE_TUF_PRINCIPLES_V1_OK=1"; true; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1.txt"

if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"
  exit 1
fi
grep -q '^SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

TUF_META_ROOT="$(grep -E '^TUF_META_ROOT=' "$SSOT" | head -n1 | sed 's/^TUF_META_ROOT=//' | tr -d '\r')"
[ -n "$TUF_META_ROOT" ] || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

# Required role files (SSOT REQUIRE_ROLE_* = 1)
for role in root targets snapshot timestamp; do
  f="$TUF_META_ROOT/${role}.json"
  if [ ! -f "$f" ]; then
    echo "ERROR_CODE=TUF_ROLE_MISSING"
    echo "HIT_ROLE=${role}"
    exit 1
  fi
done

# JSON valid + minimal field presence
for role in root targets snapshot timestamp; do
  f="$TUF_META_ROOT/${role}.json"
  set +e
  node -e "
    const fs = require('fs');
    let d;
    try { d = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); } catch (e) { process.exit(1); }
    if (!d || typeof d !== 'object') process.exit(1);
    if (!d.signed || typeof d.signed !== 'object') process.exit(2);
    if (!d.signed.expires) process.exit(2);
    if (process.argv[1].includes('root.json') && (!d.signed.roles || typeof d.signed.roles !== 'object')) process.exit(2);
    process.exit(0);
  " "$f" 2>/dev/null
  r=$?
  set -e
  if [ "$r" -eq 1 ]; then
    echo "ERROR_CODE=TUF_JSON_INVALID"
    echo "HIT_FILE=$f"
    exit 1
  fi
  if [ "$r" -eq 2 ]; then
    echo "ERROR_CODE=TUF_POLICY_MISSING_FIELD"
    echo "HIT_FIELD=expires_or_roles"
    exit 1
  fi
done

SECURE_UPDATE_TUF_PRINCIPLES_V1_OK=1
exit 0
