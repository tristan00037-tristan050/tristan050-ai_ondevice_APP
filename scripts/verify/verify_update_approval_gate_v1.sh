#!/usr/bin/env bash
set -euo pipefail

# P22-AI-11: UPDATE_APPROVAL_GATE_V1 verifier
UPDATE_APPROVAL_GATE_V1_OK=0
trap 'echo "UPDATE_APPROVAL_GATE_V1_OK=${UPDATE_APPROVAL_GATE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

GATE="docs/ops/contracts/UPDATE_APPROVAL_GATE_V1.json"
[[ -f "$GATE" ]] || { echo "ERROR_CODE=UPDATE_APPROVAL_GATE_MISSING"; echo "HIT_PATH=$GATE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$GATE" <<'PYEOF'
import json, sys

gate_path = sys.argv[1]

try:
    with open(gate_path, 'r', encoding='utf-8') as f:
        gate = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=UPDATE_APPROVAL_GATE_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

if gate.get("schema_version") not in (1, 2):
    print("ERROR_CODE=UPDATE_APPROVAL_GATE_SCHEMA_VERSION_INVALID")
    sys.exit(1)

REQUIRED_FIELDS = [
    "gate_id", "required_approvals", "required_checks",
    "auto_approve_if_all_checks_pass", "block_on_missing_weights",
]
for field in REQUIRED_FIELDS:
    if field not in gate:
        print(f"ERROR_CODE=UPDATE_APPROVAL_GATE_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

required_checks = gate.get("required_checks", [])
if not isinstance(required_checks, list) or len(required_checks) == 0:
    print("ERROR_CODE=UPDATE_APPROVAL_GATE_CHECKS_EMPTY")
    sys.exit(1)
PYEOF

# Validate required_checks scripts actually exist
"$PYTHON_BIN" - "$GATE" "$ROOT" <<'PYEOF'
import json, sys, os

gate_path, root = sys.argv[1], sys.argv[2]
with open(gate_path, 'r', encoding='utf-8') as f:
    gate = json.load(f)

failed = 0
for check_name in gate.get("required_checks", []):
    script_path = os.path.join(root, "scripts", "verify", f"{check_name}.sh")
    if not os.path.isfile(script_path):
        print(f"ERROR_CODE=UPDATE_APPROVAL_GATE_CHECK_SCRIPT_MISSING")
        print(f"MISSING_SCRIPT=scripts/verify/{check_name}.sh")
        failed = 1

if failed:
    sys.exit(1)
PYEOF

UPDATE_APPROVAL_GATE_V1_OK=1
exit 0
