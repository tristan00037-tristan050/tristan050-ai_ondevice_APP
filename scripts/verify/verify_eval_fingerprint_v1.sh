#!/usr/bin/env bash
set -euo pipefail

# P22-AI-09 / P23-P0B-06: EVAL_FINGERPRINT_V1 verifier
EVAL_FINGERPRINT_V1_OK=0
trap 'echo "EVAL_FINGERPRINT_V1_OK=${EVAL_FINGERPRINT_V1_OK}"' EXIT

ENFORCE="${EVAL_FINGERPRINT_ENFORCE:-0}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

PACK_IDS="micro_default small_default"
REQUIRED_FIELDS="fingerprint_version pack_id eval_suite_id input_corpus_digest output_digest status"

set +e
"$PYTHON_BIN" - "$ENFORCE" "$PACK_IDS" "$REQUIRED_FIELDS" <<'PYEOF'
import json, sys, re

enforce, pack_ids_str, required_fields_str = sys.argv[1], sys.argv[2], sys.argv[3]

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

failed = 0
has_pending = False

for pack_id in pack_ids_str.split():
    ef = f"packs/{pack_id}/eval_fingerprint.json"

    try:
        with open(ef, 'r', encoding='utf-8') as f:
            doc = json.load(f)
    except FileNotFoundError:
        print(f"ERROR_CODE=EVAL_FINGERPRINT_MISSING")
        print(f"HIT_PATH={ef}")
        failed = 1
        continue
    except Exception as e:
        print(f"ERROR_CODE=EVAL_FINGERPRINT_JSON_INVALID")
        print(f"HIT_PATH={ef}")
        print(f"DETAIL={e}")
        failed = 1
        continue

    for field in required_fields_str.split():
        if field not in doc:
            print(f"ERROR_CODE=EVAL_FINGERPRINT_FIELD_MISSING")
            print(f"PACK={pack_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1

    if failed:
        continue

    # pack_id must match directory name
    if doc.get("pack_id") != pack_id:
        print(f"ERROR_CODE=EVAL_FINGERPRINT_PACK_ID_MISMATCH")
        print(f"EXPECTED={pack_id}")
        print(f"ACTUAL={doc.get('pack_id')}")
        failed = 1
        continue

    # fingerprint_version must be eval_v1
    if doc.get("fingerprint_version") != "eval_v1":
        print(f"ERROR_CODE=EVAL_FINGERPRINT_VERSION_INVALID")
        print(f"PACK={pack_id}")
        print(f"ACTUAL={doc.get('fingerprint_version')}")
        failed = 1
        continue

    # eval_suite_id must be present and non-empty
    if not doc.get("eval_suite_id"):
        print(f"ERROR_CODE=EVAL_FINGERPRINT_SUITE_ID_MISSING")
        print(f"PACK={pack_id}")
        failed = 1
        continue

    # status must not be "pending_ai09" (not activated)
    if doc.get("status") == "pending_ai09":
        print(f"ERROR_CODE=EVAL_FINGERPRINT_NOT_ACTIVATED")
        print(f"PACK={pack_id}")
        failed = 1
        continue

    status = doc.get("status", "")

    if status == "pending_real_weights":
        has_pending = True
        continue  # skip further validation for pending packs

    if status == "verified":
        # eval_score and eval_passed must be non-null when verified
        if doc.get("eval_score") is None:
            print(f"ERROR_CODE=EVAL_FINGERPRINT_SCORE_NULL_ON_VERIFIED")
            print(f"PACK={pack_id}")
            failed = 1
        if doc.get("eval_passed") is None:
            print(f"ERROR_CODE=EVAL_FINGERPRINT_PASSED_NULL_ON_VERIFIED")
            print(f"PACK={pack_id}")
            failed = 1
    # other statuses are accepted (future extension)

if failed:
    sys.exit(1)

# has_pending: ENFORCE=0 → skip (exit 2), ENFORCE=1 → block
if has_pending:
    if enforce == "1":
        print("ERROR_CODE=EVAL_FINGERPRINT_PENDING_BLOCKED")
        print("NOTE=Real eval fingerprints required before release")
        sys.exit(1)
    else:
        sys.exit(2)  # skip

sys.exit(0)
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "EVAL_FINGERPRINT_V1_SKIPPED=1"
  EVAL_FINGERPRINT_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

EVAL_FINGERPRINT_V1_OK=1
exit 0
