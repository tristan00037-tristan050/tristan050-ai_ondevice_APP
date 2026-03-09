#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-P0-01: ENTERPRISE_SCOPE_V1 verifier
ENTERPRISE_SCOPE_V1_OK=0
trap 'echo "ENTERPRISE_SCOPE_V1_OK=${ENTERPRISE_SCOPE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONTRACT="docs/ops/contracts/ENTERPRISE_SCOPE_V1.json"
[[ -f "$CONTRACT" ]] || { echo "ERROR_CODE=ENTERPRISE_SCOPE_CONTRACT_MISSING"; echo "HIT_PATH=$CONTRACT"; exit 1; }

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

# scope_hierarchy: 4 levels required
hierarchy = doc.get("scope_hierarchy", {})
REQUIRED_LEVELS = ["org_scope", "department_scope", "team_scope", "user_scope"]
for level in REQUIRED_LEVELS:
    if level not in hierarchy:
        print(f"ERROR_CODE=ENTERPRISE_SCOPE_LEVEL_MISSING")
        print(f"MISSING_FIELD={level}")
        failed = 1

# policy_override_order required
override_order = doc.get("policy_override_order")
if not isinstance(override_order, list):
    print("ERROR_CODE=ENTERPRISE_SCOPE_POLICY_OVERRIDE_ORDER_MISSING")
    failed = 1
else:
    REQUIRED_ENTRIES = ["org_default", "department_override", "team_override", "user_override"]
    for entry in REQUIRED_ENTRIES:
        if entry not in override_order:
            print(f"ERROR_CODE=ENTERPRISE_SCOPE_POLICY_OVERRIDE_ENTRY_MISSING")
            print(f"MISSING_ENTRY={entry}")
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
TS_FILE="tools/enterprise/enterprise_scope_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=ENTERPRISE_SCOPE_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

REQUIRED_SYMBOLS=(
  "resolveEffectiveScope"
  "assertScopeHierarchy"
  "assertPolicyOverrideOrder"
  "assertEnterpriseScopeV1"
  "ScopeLevel"
  "ScopeHierarchy"
  "EnterpriseScopeV1"
)
for sym in "${REQUIRED_SYMBOLS[@]}"; do
  grep -q "$sym" "$TS_FILE" || { echo "ERROR_CODE=ENTERPRISE_SCOPE_TS_SYMBOL_MISSING"; echo "MISSING_SYMBOL=$sym"; exit 1; }
done

ENTERPRISE_SCOPE_V1_OK=1
exit 0
