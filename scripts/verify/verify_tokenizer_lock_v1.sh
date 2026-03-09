#!/usr/bin/env bash
set -euo pipefail

# P23-P0A-06: TOKENIZER_TEMPLATE_LOCK_V1 verifier
TOKENIZER_LOCK_V1_OK=0
trap 'echo "TOKENIZER_LOCK_V1_OK=${TOKENIZER_LOCK_V1_OK}"' EXIT

ENFORCE="${TOKENIZER_LOCK_ENFORCE:-0}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/TOKENIZER_LOCK_POLICY_V1.json"
[[ -f "$POLICY" ]] || { echo "ERROR_CODE=TOKENIZER_LOCK_POLICY_MISSING"; echo "HIT_PATH=$POLICY"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

# Exit codes: 0=ok, 1=error, 2=skip(placeholder+enforce=0)
set +e
"$PYTHON_BIN" - "$POLICY" "$ENFORCE" <<'PYEOF'
import json, sys, glob

policy_path, enforce = sys.argv[1], sys.argv[2]

with open(policy_path, 'r', encoding='utf-8') as f:
    policy = json.load(f)

REQUIRED_DIGEST_FIELDS = policy.get("required_digests", [])
PACK_MANIFESTS = glob.glob("packs/*/manifest.json")
PLACEHOLDER = "REQUIRED"

failed = 0
has_placeholder = False

for manifest_path in sorted(PACK_MANIFESTS):
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"ERROR_CODE=TOKENIZER_LOCK_MANIFEST_JSON_INVALID")
        print(f"HIT_PATH={manifest_path}")
        failed = 1
        continue

    pack_id = manifest.get("pack_id", manifest_path)
    for field in REQUIRED_DIGEST_FIELDS:
        if field not in manifest:
            print(f"ERROR_CODE=TOKENIZER_LOCK_FIELD_MISSING")
            print(f"PACK={pack_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1
        elif manifest[field] == PLACEHOLDER:
            has_placeholder = True

if failed:
    sys.exit(1)

# Placeholder present: ENFORCE=0 → skip, ENFORCE=1 → block
if has_placeholder:
    if enforce == "1":
        print("ERROR_CODE=TOKENIZER_LOCK_PLACEHOLDER_VALUES_PRESENT")
        print("NOTE=Real tokenizer digests required before release")
        sys.exit(1)
    else:
        sys.exit(2)  # skip
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "TOKENIZER_LOCK_V1_SKIPPED=1"
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

TOKENIZER_LOCK_V1_OK=1
exit 0
