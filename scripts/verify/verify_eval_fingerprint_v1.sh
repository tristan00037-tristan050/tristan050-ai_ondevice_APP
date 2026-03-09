#!/usr/bin/env bash
set -euo pipefail

# P22-AI-09: EVAL_FINGERPRINT_V1 verifier
EVAL_FINGERPRINT_V1_OK=0
trap 'echo "EVAL_FINGERPRINT_V1_OK=${EVAL_FINGERPRINT_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

PACK_IDS="micro_default small_default"
REQUIRED_FIELDS="fingerprint_version pack_id eval_suite_id input_corpus_digest output_digest status"

failed=0
for pack_id in $PACK_IDS; do
  ef="packs/${pack_id}/eval_fingerprint.json"
  [[ -f "$ef" ]] || { echo "ERROR_CODE=EVAL_FINGERPRINT_MISSING"; echo "HIT_PATH=$ef"; failed=1; continue; }

  "$PYTHON_BIN" - "$ef" "$pack_id" "$REQUIRED_FIELDS" <<'PYEOF'
import json, sys

ef_path, pack_id, required_fields_str = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    with open(ef_path, 'r', encoding='utf-8') as f:
        doc = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=EVAL_FINGERPRINT_JSON_INVALID")
    print(f"HIT_PATH={ef_path}")
    print(f"DETAIL={e}")
    sys.exit(1)

for field in required_fields_str.split():
    if field not in doc:
        print(f"ERROR_CODE=EVAL_FINGERPRINT_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# pack_id must match directory name
if doc.get("pack_id") != pack_id:
    print(f"ERROR_CODE=EVAL_FINGERPRINT_PACK_ID_MISMATCH")
    print(f"EXPECTED={pack_id}")
    print(f"ACTUAL={doc.get('pack_id')}")
    sys.exit(1)

# fingerprint_version must be eval_v1
if doc.get("fingerprint_version") != "eval_v1":
    print(f"ERROR_CODE=EVAL_FINGERPRINT_VERSION_INVALID")
    print(f"PACK={pack_id}")
    print(f"ACTUAL={doc.get('fingerprint_version')}")
    sys.exit(1)

# eval_suite_id must be present and non-empty
if not doc.get("eval_suite_id"):
    print(f"ERROR_CODE=EVAL_FINGERPRINT_SUITE_ID_MISSING")
    print(f"PACK={pack_id}")
    sys.exit(1)

# status must not be "pending_ai09" (activated in AI-09)
if doc.get("status") == "pending_ai09":
    print(f"ERROR_CODE=EVAL_FINGERPRINT_NOT_ACTIVATED")
    print(f"PACK={pack_id}")
    sys.exit(1)
PYEOF
  rc=$?
  [[ $rc -eq 0 ]] || { failed=1; }
done

[[ "$failed" -eq 0 ]] || exit 1

EVAL_FINGERPRINT_V1_OK=1
exit 0
