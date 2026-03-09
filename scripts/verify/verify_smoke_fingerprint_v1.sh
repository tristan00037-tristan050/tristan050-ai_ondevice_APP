#!/usr/bin/env bash
set -euo pipefail

# P23-P0B-05: SMOKE_INFER_AND_FINGERPRINT_V1 verifier
SMOKE_FINGERPRINT_V1_OK=0
trap 'echo "SMOKE_FINGERPRINT_V1_OK=${SMOKE_FINGERPRINT_V1_OK}"' EXIT

ENFORCE="${SMOKE_FINGERPRINT_ENFORCE:-0}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

set +e
"$PYTHON_BIN" - "$ENFORCE" <<'PYEOF'
import json, sys, glob, re

enforce = sys.argv[1]

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
PLACEHOLDER_VALUES = {"COMPUTED_AT_PACK_BUILD_TIME", "REQUIRED", "pending_real_weights"}

smoke_files = sorted(glob.glob("packs/*/smoke_fingerprint.json"))

if not smoke_files:
    print("ERROR_CODE=SMOKE_FINGERPRINT_NO_FILES_FOUND")
    sys.exit(1)

failed = 0
has_pending = False

for sf_path in smoke_files:
    try:
        with open(sf_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR_CODE=SMOKE_FINGERPRINT_JSON_INVALID")
        print(f"HIT_PATH={sf_path}")
        print(f"DETAIL={e}")
        failed = 1
        continue

    # fingerprint_version must be present
    if "fingerprint_version" not in doc:
        print(f"ERROR_CODE=SMOKE_FINGERPRINT_VERSION_MISSING")
        print(f"HIT_PATH={sf_path}")
        failed = 1
        continue

    # pack_id must be present
    if "pack_id" not in doc:
        print(f"ERROR_CODE=SMOKE_FINGERPRINT_PACK_ID_MISSING")
        print(f"HIT_PATH={sf_path}")
        failed = 1
        continue

    status = doc.get("status", "")

    if status == "pending_real_weights":
        has_pending = True
        continue  # skip further checks for pending packs

    if status == "verified":
        # input_digest and output_digest must be real sha256 hex
        for dig_field in ("input_digest", "output_digest"):
            val = doc.get(dig_field, "")
            if not SHA256_RE.match(val):
                print(f"ERROR_CODE=SMOKE_FINGERPRINT_DIGEST_INVALID")
                print(f"HIT_PATH={sf_path}")
                print(f"FIELD={dig_field}")
                print(f"VALUE={val}")
                failed = 1
    else:
        print(f"ERROR_CODE=SMOKE_FINGERPRINT_STATUS_UNKNOWN")
        print(f"HIT_PATH={sf_path}")
        print(f"STATUS={status}")
        failed = 1

if failed:
    sys.exit(1)

# has_pending: ENFORCE=0 → skip (exit 2), ENFORCE=1 → block (exit 1)
if has_pending:
    if enforce == "1":
        print("ERROR_CODE=SMOKE_FINGERPRINT_PENDING_BLOCKED")
        print("NOTE=Real smoke fingerprints required before release")
        sys.exit(1)
    else:
        sys.exit(2)  # skip

sys.exit(0)
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "SMOKE_FINGERPRINT_V1_SKIPPED=1"
  SMOKE_FINGERPRINT_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

SMOKE_FINGERPRINT_V1_OK=1
exit 0
