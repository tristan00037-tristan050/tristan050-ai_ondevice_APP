#!/usr/bin/env bash
set -euo pipefail

# P23-P1-01: THERMAL_ENERGY_PROFILE_V1 verifier
THERMAL_ENERGY_PROFILE_V1_OK=0
trap 'echo "THERMAL_ENERGY_PROFILE_V1_OK=${THERMAL_ENERGY_PROFILE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/THERMAL_ENERGY_PROFILE_V1.json"
[[ -f "$POLICY" ]] || { echo "ERROR_CODE=THERMAL_ENERGY_PROFILE_MISSING"; echo "HIT_PATH=$POLICY"; exit 1; }

TS_FILE="tools/device-profile/thermal_profile_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=THERMAL_PROFILE_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$POLICY" <<'PYEOF'
import json, sys

policy_path = sys.argv[1]

try:
    with open(policy_path, 'r', encoding='utf-8') as f:
        policy = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=THERMAL_ENERGY_PROFILE_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

REQUIRED_FIELDS = [
    "schema_version", "profile_id", "thermal_headroom_floor",
    "sustained_perf_required_headroom", "downgrade_on_serious",
    "downgrade_on_critical", "block_high_power_on_low_battery",
    "block_high_power_on_low_power_mode"
]

for field in REQUIRED_FIELDS:
    if field not in policy:
        print(f"ERROR_CODE=THERMAL_ENERGY_PROFILE_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# thermal_headroom_floor must be in [0, 1]
floor = policy.get("thermal_headroom_floor")
if not isinstance(floor, (int, float)) or floor < 0 or floor > 1.0:
    print(f"ERROR_CODE=THERMAL_HEADROOM_FLOOR_OUT_OF_RANGE")
    print(f"VALUE={floor}")
    sys.exit(1)

# sustained_perf_required_headroom must be in [0, 1]
req = policy.get("sustained_perf_required_headroom")
if not isinstance(req, (int, float)) or req < 0 or req > 1.0:
    print(f"ERROR_CODE=SUSTAINED_PERF_HEADROOM_OUT_OF_RANGE")
    print(f"VALUE={req}")
    sys.exit(1)
PYEOF

# Verify required exports exist in TypeScript file
failed=0
for symbol in "ThermalState" "BatteryBucket" "PowerClass" "ThermalEnergyProfile" \
              "classifyThermalState" "isSustainedPerfAvailable" "mockThermalProfile"; do
  if ! grep -q "$symbol" "$TS_FILE"; then
    echo "ERROR_CODE=THERMAL_PROFILE_TS_SYMBOL_MISSING"
    echo "MISSING_SYMBOL=${symbol}"
    failed=1
  fi
done

[[ "$failed" -eq 0 ]] || exit 1

THERMAL_ENERGY_PROFILE_V1_OK=1
exit 0
