#!/usr/bin/env bash
set -euo pipefail

# P24-R-02: verify_experimental_native_lowbit_v1.sh
# EXPERIMENTAL_NATIVE_LOWBIT_V1.json 존재 확인 + production_enabled=false 강제
# native_ultra_low_bit.status=research 확인

EXPERIMENTAL_NATIVE_LOWBIT_V1_OK=0
trap 'echo "EXPERIMENTAL_NATIVE_LOWBIT_V1_OK=${EXPERIMENTAL_NATIVE_LOWBIT_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY_FILE="docs/ops/contracts/EXPERIMENTAL_NATIVE_LOWBIT_V1.json"
TS_FILE="tools/experimental/quantization_strategy_v1.ts"

set +e
python3 - "$POLICY_FILE" "$TS_FILE" <<'PYEOF'
import json, sys, os

policy_path, ts_path = sys.argv[1], sys.argv[2]

if not os.path.isfile(policy_path):
    print(f"ERROR_CODE=EXPERIMENTAL_NATIVE_LOWBIT_POLICY_MISSING")
    print(f"HIT_PATH={policy_path}")
    sys.exit(1)

with open(policy_path, encoding='utf-8') as f:
    policy = json.load(f)

required_fields = [
    "schema_version", "experiment_id", "status",
    "production_enabled", "quantization_strategies", "activation_condition"
]
for field in required_fields:
    if field not in policy:
        print(f"ERROR_CODE=NATIVE_LOWBIT_POLICY_FIELD_MISSING:{field}")
        sys.exit(1)

# BLOCK: production_enabled must be false
if policy["production_enabled"] is not False:
    print("ERROR_CODE=NATIVE_LOWBIT_PRODUCTION_ENABLED_BLOCKED")
    print("DETAIL=production_enabled must be false in experimental lane")
    sys.exit(1)

# native_ultra_low_bit must remain research
strategies = policy.get("quantization_strategies", {})
native = strategies.get("native_ultra_low_bit", {})
if native.get("status") != "research":
    print(f"ERROR_CODE=NATIVE_ULTRA_LOW_BIT_STATUS_NOT_RESEARCH")
    print(f"ACTUAL={native.get('status')}")
    sys.exit(1)

if not os.path.isfile(ts_path):
    print(f"ERROR_CODE=NATIVE_LOWBIT_TS_MISSING")
    print(f"HIT_PATH={ts_path}")
    sys.exit(1)

ts_src = open(ts_path, encoding='utf-8').read()
required_symbols = [
    "QuantizationStatus",
    "QuantizationStrategy",
    "QUANTIZATION_REGISTRY",
    "getProductionStrategies",
    "assertNotResearchInProduction",
    "RESEARCH_STRATEGY_IN_PRODUCTION",
    "UNKNOWN_QUANTIZATION_STRATEGY",
    "is_production_allowed",
]
for sym in required_symbols:
    if sym not in ts_src:
        print(f"ERROR_CODE=NATIVE_LOWBIT_TS_SYMBOL_MISSING:{sym}")
        sys.exit(1)

print("STATUS=ok")
print("EXPERIMENTAL_NATIVE_LOWBIT_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -ne 0 ]; then
  exit 1
fi

EXPERIMENTAL_NATIVE_LOWBIT_V1_OK=1
exit 0
