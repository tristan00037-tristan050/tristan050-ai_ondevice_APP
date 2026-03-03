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

ENFORCE="${SECURE_UPDATE_TUF_ENFORCE:-0}"

ROOT_JSON="${TUF_META_ROOT}/root.json"
TARGETS_JSON="${TUF_META_ROOT}/targets.json"
SNAPSHOT_JSON="${TUF_META_ROOT}/snapshot.json"
TIMESTAMP_JSON="${TUF_META_ROOT}/timestamp.json"

# if missing, SKIP by default; ENFORCE=1 => BLOCK
if [ ! -f "$ROOT_JSON" ] || [ ! -f "$TARGETS_JSON" ] || [ ! -f "$SNAPSHOT_JSON" ] || [ ! -f "$TIMESTAMP_JSON" ]; then
  if [ "$ENFORCE" = "1" ]; then
    echo "ERROR_CODE=TUF_ROLE_MISSING"
    if [ ! -f "$ROOT_JSON" ]; then echo "HIT_ROLE=root"; exit 1; fi
    if [ ! -f "$TARGETS_JSON" ]; then echo "HIT_ROLE=targets"; exit 1; fi
    if [ ! -f "$SNAPSHOT_JSON" ]; then echo "HIT_ROLE=snapshot"; exit 1; fi
    if [ ! -f "$TIMESTAMP_JSON" ]; then echo "HIT_ROLE=timestamp"; exit 1; fi
    exit 1
  fi
  echo "SECURE_UPDATE_TUF_PRINCIPLES_V1_SKIPPED=1"
  exit 0
fi

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
