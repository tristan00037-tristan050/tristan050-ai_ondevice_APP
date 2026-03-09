#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-P0-03: PACK_ASSIGNMENT_POLICY_V1 verifier
PACK_ASSIGNMENT_POLICY_V1_OK=0
trap 'echo "PACK_ASSIGNMENT_POLICY_V1_OK=${PACK_ASSIGNMENT_POLICY_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONTRACT="docs/ops/contracts/PACK_ASSIGNMENT_POLICY_V1.json"
[[ -f "$CONTRACT" ]] || { echo "ERROR_CODE=PACK_ASSIGNMENT_POLICY_CONTRACT_MISSING"; echo "HIT_PATH=$CONTRACT"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

set +e
"$PYTHON_BIN" - "$CONTRACT" <<'PYEOF'
import json, sys

contract_path = sys.argv[1]

with open(contract_path, 'r', encoding='utf-8') as f:
    doc = json.load(f)

failed = 0

REQUIRED_FIELDS = [
    "required_fields",
    "valid_rollout_rings",
    "enforcement"
]
for field in REQUIRED_FIELDS:
    if field not in doc:
        print(f"ERROR_CODE=PACK_ASSIGNMENT_POLICY_CONTRACT_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        failed = 1

# Validate required_fields list covers expected entries
expected_policy_fields = {
    "policy_id", "target_groups", "target_device_classes",
    "rollout_ring", "minimum_app_version", "offline_capable_required", "policy_digest"
}
actual_required = set(doc.get("required_fields", []))
for f in expected_policy_fields:
    if f not in actual_required:
        print(f"ERROR_CODE=PACK_ASSIGNMENT_POLICY_REQUIRED_FIELD_ENTRY_MISSING")
        print(f"MISSING_ENTRY={f}")
        failed = 1

# Validate rollout rings cover all 4
expected_rings = {"ring0_canary", "ring1_team", "ring2_department", "ring3_org"}
actual_rings = set(doc.get("valid_rollout_rings", []))
for ring in expected_rings:
    if ring not in actual_rings:
        print(f"ERROR_CODE=PACK_ASSIGNMENT_POLICY_ROLLOUT_RING_MISSING")
        print(f"MISSING_RING={ring}")
        failed = 1

if failed:
    sys.exit(1)
PYEOF
py_rc=$?
set -e

if [ $py_rc -ne 0 ]; then
  exit 1
fi

# Validate TS symbols
TS_FILE="tools/enterprise/pack_assignment_policy_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=PACK_ASSIGNMENT_POLICY_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

REQUIRED_SYMBOLS=(
  "PackAssignmentPolicyV1"
  "RolloutRing"
  "assertPackAssignmentPolicyV1"
  "isPrincipalCoveredByPolicy"
  "isDeviceClassCoveredByPolicy"
  "PACK_ASSIGNMENT_POLICY_FIELD_MISSING"
  "PACK_ASSIGNMENT_POLICY_INVALID_ROLLOUT_RING"
  "ring0_canary"
  "ring1_team"
  "ring2_department"
  "ring3_org"
)
for sym in "${REQUIRED_SYMBOLS[@]}"; do
  grep -q "$sym" "$TS_FILE" || { echo "ERROR_CODE=PACK_ASSIGNMENT_POLICY_TS_SYMBOL_MISSING"; echo "MISSING_SYMBOL=$sym"; exit 1; }
done

PACK_ASSIGNMENT_POLICY_V1_OK=1
exit 0
