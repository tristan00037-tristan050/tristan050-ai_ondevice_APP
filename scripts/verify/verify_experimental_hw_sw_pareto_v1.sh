#!/usr/bin/env bash
set -euo pipefail

# P24-R-03: verify_experimental_hw_sw_pareto_v1.sh
# EXPERIMENTAL_HW_SW_CODESIGN_V1.json 존재 확인 + production_enabled=false 강제
# status=research 확인

EXPERIMENTAL_HW_SW_PARETO_V1_OK=0
trap 'echo "EXPERIMENTAL_HW_SW_PARETO_V1_OK=${EXPERIMENTAL_HW_SW_PARETO_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY_FILE="docs/ops/contracts/EXPERIMENTAL_HW_SW_CODESIGN_V1.json"
TS_FILE="tools/experimental/hw_sw_pareto_v1.ts"

set +e
python3 - "$POLICY_FILE" "$TS_FILE" <<'PYEOF'
import json, sys, os

policy_path, ts_path = sys.argv[1], sys.argv[2]

if not os.path.isfile(policy_path):
    print(f"ERROR_CODE=EXPERIMENTAL_HW_SW_PARETO_POLICY_MISSING")
    print(f"HIT_PATH={policy_path}")
    sys.exit(1)

with open(policy_path, encoding='utf-8') as f:
    policy = json.load(f)

required_fields = [
    "schema_version", "experiment_id", "status",
    "production_enabled", "target_dimensions", "activation_condition"
]
for field in required_fields:
    if field not in policy:
        print(f"ERROR_CODE=HW_SW_PARETO_POLICY_FIELD_MISSING:{field}")
        sys.exit(1)

# BLOCK: production_enabled must be false
if policy["production_enabled"] is not False:
    print("ERROR_CODE=HW_SW_PARETO_PRODUCTION_ENABLED_BLOCKED")
    print("DETAIL=production_enabled must be false in experimental lane")
    sys.exit(1)

# status must be research
if policy["status"] != "research":
    print(f"ERROR_CODE=HW_SW_PARETO_STATUS_NOT_RESEARCH")
    print(f"ACTUAL={policy['status']}")
    sys.exit(1)

if not os.path.isfile(ts_path):
    print(f"ERROR_CODE=HW_SW_PARETO_TS_MISSING")
    print(f"HIT_PATH={ts_path}")
    sys.exit(1)

ts_src = open(ts_path, encoding='utf-8').read()
required_symbols = [
    "ParetoPoint",
    "computeParetoFrontier",
    "getParetoOptimal",
    "is_pareto_optimal",
    "accuracy_score",
    "latency_p95_ms",
    "thermal_risk",
]
for sym in required_symbols:
    if sym not in ts_src:
        print(f"ERROR_CODE=HW_SW_PARETO_TS_SYMBOL_MISSING:{sym}")
        sys.exit(1)

print("STATUS=ok")
print("EXPERIMENTAL_HW_SW_PARETO_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -ne 0 ]; then
  exit 1
fi

EXPERIMENTAL_HW_SW_PARETO_V1_OK=1
exit 0
