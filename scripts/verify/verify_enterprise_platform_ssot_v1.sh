#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-P0-04: ENTERPRISE_PLATFORM_SSOT_V1 verifier
ENTERPRISE_PLATFORM_SSOT_V1_OK=0
trap 'echo "ENTERPRISE_PLATFORM_SSOT_V1_OK=${ENTERPRISE_PLATFORM_SSOT_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ENTERPRISE_PLATFORM_SSOT_V1.json"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_MISSING"; echo "HIT_PATH=$SSOT"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

set +e
"$PYTHON_BIN" - "$SSOT" <<'PYEOF'
import json, sys, os, glob, subprocess

ssot_path = sys.argv[1]
root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()

with open(ssot_path, 'r', encoding='utf-8') as f:
    doc = json.load(f)

failed = 0

contracts = doc.get("contracts")
if not isinstance(contracts, list) or len(contracts) == 0:
    print("ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_CONTRACTS_MISSING")
    sys.exit(1)

REQUIRED_CONTRACT_FIELDS = ["contract_id", "path", "verifier", "dod_key", "status"]
VALID_STATUSES = {"active", "pending_real_weights", "stub"}

for contract in contracts:
    cid = contract.get("contract_id", "<unknown>")
    for field in REQUIRED_CONTRACT_FIELDS:
        if field not in contract:
            print(f"ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_CONTRACT_FIELD_MISSING")
            print(f"CONTRACT={cid}")
            print(f"MISSING_FIELD={field}")
            failed = 1

    status = contract.get("status", "")
    if status not in VALID_STATUSES:
        print(f"ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_INVALID_STATUS")
        print(f"CONTRACT={cid}")
        print(f"STATUS={status}")
        failed = 1

    # Verifier file must exist (skip glob paths)
    verifier = contract.get("verifier", "")
    if verifier and "*" not in verifier:
        verifier_path = os.path.join(root, verifier)
        if not os.path.isfile(verifier_path):
            print(f"ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_VERIFIER_MISSING")
            print(f"CONTRACT={cid}")
            print(f"VERIFIER={verifier}")
            failed = 1

    # TS impl must exist if specified and non-null
    ts_impl = contract.get("ts_impl")
    if ts_impl and "*" not in ts_impl:
        ts_path = os.path.join(root, ts_impl)
        if not os.path.isfile(ts_path):
            print(f"ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_TS_IMPL_MISSING")
            print(f"CONTRACT={cid}")
            print(f"TS_IMPL={ts_impl}")
            failed = 1

if failed:
    sys.exit(1)

# Check required DOD keys present
required_dod_keys = {
    "ENTERPRISE_SCOPE_V1_OK",
    "DEVICE_CLASS_REGISTRY_V1_OK",
    "PACK_ASSIGNMENT_POLICY_V1_OK",
}
actual_dod_keys = {c.get("dod_key") for c in contracts}
for key in required_dod_keys:
    if key not in actual_dod_keys:
        print(f"ERROR_CODE=ENTERPRISE_PLATFORM_SSOT_DOD_KEY_MISSING")
        print(f"MISSING_KEY={key}")
        sys.exit(1)
PYEOF
py_rc=$?
set -e

if [ $py_rc -ne 0 ]; then
  exit 1
fi

ENTERPRISE_PLATFORM_SSOT_V1_OK=1
exit 0
