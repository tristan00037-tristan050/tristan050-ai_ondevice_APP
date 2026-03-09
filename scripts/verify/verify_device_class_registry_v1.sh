#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-P0-02: DEVICE_CLASS_REGISTRY_V1 verifier
DEVICE_CLASS_REGISTRY_V1_OK=0
trap 'echo "DEVICE_CLASS_REGISTRY_V1_OK=${DEVICE_CLASS_REGISTRY_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONTRACT="docs/ops/contracts/DEVICE_CLASS_REGISTRY_V1.json"
[[ -f "$CONTRACT" ]] || { echo "ERROR_CODE=DEVICE_CLASS_REGISTRY_CONTRACT_MISSING"; echo "HIT_PATH=$CONTRACT"; exit 1; }

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

device_classes = doc.get("device_classes")
if not isinstance(device_classes, list) or len(device_classes) == 0:
    print("ERROR_CODE=DEVICE_CLASS_REGISTRY_EMPTY_OR_MISSING")
    sys.exit(1)

REQUIRED_FIELDS = ["device_class_id", "display_name", "min_ram_gb", "min_npu_tops", "allowed_pack_ids", "power_class"]
VALID_POWER_CLASSES = {"high", "medium", "low"}

for entry in device_classes:
    dc_id = entry.get("device_class_id", "<unknown>")
    for field in REQUIRED_FIELDS:
        if field not in entry:
            print(f"ERROR_CODE=DEVICE_CLASS_ENTRY_FIELD_MISSING")
            print(f"DEVICE_CLASS={dc_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1
    allowed = entry.get("allowed_pack_ids", [])
    if not isinstance(allowed, list) or len(allowed) == 0:
        print(f"ERROR_CODE=DEVICE_CLASS_ALLOWED_PACKS_EMPTY")
        print(f"DEVICE_CLASS={dc_id}")
        failed = 1
    power = entry.get("power_class", "")
    if power not in VALID_POWER_CLASSES:
        print(f"ERROR_CODE=DEVICE_CLASS_INVALID_POWER_CLASS")
        print(f"DEVICE_CLASS={dc_id}")
        print(f"POWER_CLASS={power}")
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
TS_FILE="tools/enterprise/device_class_registry_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=DEVICE_CLASS_REGISTRY_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

REQUIRED_SYMBOLS=(
  "DeviceClassEntry"
  "DeviceClassRegistryV1"
  "getDeviceClass"
  "assertPackAllowedForDeviceClass"
  "assertDeviceClassRegistryV1"
  "DEVICE_CLASS_NOT_FOUND"
  "DEVICE_CLASS_PACK_NOT_ALLOWED"
)
for sym in "${REQUIRED_SYMBOLS[@]}"; do
  grep -q "$sym" "$TS_FILE" || { echo "ERROR_CODE=DEVICE_CLASS_REGISTRY_TS_SYMBOL_MISSING"; echo "MISSING_SYMBOL=$sym"; exit 1; }
done

DEVICE_CLASS_REGISTRY_V1_OK=1
exit 0
