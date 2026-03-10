#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-P0-02 / P25-ENT-H1: DEVICE_CLASS_REGISTRY_V1 verifier
# power_class canonical check: 'high' | 'mid' | 'low' only ('medium' → BLOCK)
DEVICE_CLASS_REGISTRY_V1_OK=0
DEVICE_CLASS_POWER_CLASS_CANONICAL_OK=0
trap 'echo "DEVICE_CLASS_REGISTRY_V1_OK=${DEVICE_CLASS_REGISTRY_V1_OK}"; echo "DEVICE_CLASS_POWER_CLASS_CANONICAL_OK=${DEVICE_CLASS_POWER_CLASS_CANONICAL_OK}"' EXIT

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
power_class_drift = False

# 1. device_classes 배열 7개 확인
device_classes = doc.get("device_classes")
if not isinstance(device_classes, list):
    print("ERROR_CODE=DEVICE_CLASS_REGISTRY_MISSING")
    sys.exit(1)

if len(device_classes) != 7:
    print(f"ERROR_CODE=DEVICE_CLASS_REGISTRY_COUNT_MISMATCH")
    print(f"EXPECTED=7 ACTUAL={len(device_classes)}")
    failed = 1

# 2. 각 class 필수 필드 확인
REQUIRED_FIELDS = ["device_class_id", "min_ram_mb", "backend_preferred", "slo"]
VALID_POWER_CLASSES = {"high", "mid", "low"}

for entry in device_classes:
    dc_id = entry.get("device_class_id", "<unknown>")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            print(f"ERROR_CODE=DEVICE_CLASS_ENTRY_FIELD_MISSING")
            print(f"DEVICE_CLASS={dc_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1

    # 3. power_class 필드가 있는 항목: 'high' | 'mid' | 'low' 만 허용
    if "power_class" in entry:
        pc = entry["power_class"]
        if pc == "medium":
            print(f"ERROR_CODE=DEVICE_CLASS_POWER_CLASS_DRIFT")
            print(f"FAILED_GUARD=DEVICE_CLASS_POWER_CLASS_DRIFT")
            print(f"DEVICE_CLASS={dc_id}")
            print(f"FOUND=medium EXPECTED=mid")
            power_class_drift = True
            failed = 1
        elif pc not in VALID_POWER_CLASSES:
            print(f"ERROR_CODE=DEVICE_CLASS_POWER_CLASS_INVALID")
            print(f"DEVICE_CLASS={dc_id}")
            print(f"POWER_CLASS={pc}")
            failed = 1

if power_class_drift:
    sys.exit(2)

if failed:
    sys.exit(1)
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "FAILED_GUARD=DEVICE_CLASS_POWER_CLASS_DRIFT"
  exit 1
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

# 4. TS 구현 파일 심볼 확인
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

# 5. 'medium' 잔존 확인 (power_class 컨텍스트)
if grep -q '"medium"' "$TS_FILE"; then
  echo "ERROR_CODE=DEVICE_CLASS_TS_MEDIUM_DRIFT"
  echo "FAILED_GUARD=DEVICE_CLASS_POWER_CLASS_DRIFT"
  exit 1
fi

DEVICE_CLASS_POWER_CLASS_CANONICAL_OK=1
DEVICE_CLASS_REGISTRY_V1_OK=1
exit 0
