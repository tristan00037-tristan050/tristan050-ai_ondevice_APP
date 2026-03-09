#!/usr/bin/env bash
set -euo pipefail

# P23-P2-01: verify_sustained_perf_gate_v1.sh
# SUSTAINED_PERF_GATE_V1.json 존재 및 필드 검증.
# status=pending_real_weights → ENFORCE=0 → SKIPPED=1
# status=verified → 각 metric이 budget 내인지 확인

SUSTAINED_PERF_GATE_V1_OK=0
trap 'echo "SUSTAINED_PERF_GATE_V1_OK=${SUSTAINED_PERF_GATE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

GATE_FILE="docs/ops/contracts/SUSTAINED_PERF_GATE_V1.json"
REPORT_FILE="docs/ops/reports/sustained_perf_latest.json"

ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$GATE_FILE" "$REPORT_FILE" "$ENFORCE" <<'PYEOF'
import json, sys, os

gate_path, report_path, enforce = sys.argv[1], sys.argv[2], sys.argv[3]

# --- Gate file validation ---
if not os.path.isfile(gate_path):
    print(f"ERROR_CODE=SUSTAINED_PERF_GATE_MISSING")
    print(f"HIT_PATH={gate_path}")
    sys.exit(1)

with open(gate_path, encoding='utf-8') as f:
    gate = json.load(f)

required_gate_fields = [
    "schema_version", "gate_id", "test_duration_minutes",
    "metrics", "pass_condition", "status"
]
for field in required_gate_fields:
    if field not in gate:
        print(f"ERROR_CODE=GATE_FIELD_MISSING:{field}")
        sys.exit(1)

required_metric_fields = [
    "latency_p95_degradation_pct_max",
    "decode_tps_degradation_pct_max",
    "thermal_headroom_floor_sustained",
    "rss_growth_pct_max"
]
for field in required_metric_fields:
    if field not in gate.get("metrics", {}):
        print(f"ERROR_CODE=GATE_METRIC_FIELD_MISSING:{field}")
        sys.exit(1)

gate_status = gate.get("status", "")

if gate_status == "pending_real_weights":
    if enforce == "0":
        print("STATUS=pending_real_weights")
        print("SKIPPED=1")
        print("NOTE=real weights 투입 후 재실행 필요")
        sys.exit(2)
    else:
        print("ERROR_CODE=SUSTAINED_PERF_GATE_PENDING_REAL_WEIGHTS_ENFORCE=1")
        sys.exit(1)

if gate_status != "verified":
    print(f"ERROR_CODE=SUSTAINED_PERF_GATE_UNKNOWN_STATUS:{gate_status}")
    sys.exit(1)

# --- Report file validation (status=verified path) ---
if not os.path.isfile(report_path):
    print(f"ERROR_CODE=SUSTAINED_PERF_REPORT_MISSING")
    print(f"HIT_PATH={report_path}")
    sys.exit(1)

with open(report_path, encoding='utf-8') as f:
    report = json.load(f)

if report.get("status") != "passed":
    print(f"ERROR_CODE=SUSTAINED_PERF_REPORT_NOT_PASSED")
    sys.exit(1)

# Validate metrics within budget
metrics = gate["metrics"]

def check_metric(name, report_val, budget, mode="max"):
    if report_val is None:
        print(f"ERROR_CODE=METRIC_NULL:{name}")
        sys.exit(1)
    if mode == "max" and report_val > budget:
        print(f"ERROR_CODE=METRIC_OVER_BUDGET:{name} actual={report_val} budget={budget}")
        sys.exit(1)
    if mode == "floor" and report_val < budget:
        print(f"ERROR_CODE=METRIC_UNDER_FLOOR:{name} actual={report_val} floor={budget}")
        sys.exit(1)

check_metric("latency_p95_degradation_pct",
             report.get("latency_p95_degradation_pct"),
             metrics["latency_p95_degradation_pct_max"], "max")
check_metric("decode_tps_degradation_pct",
             report.get("decode_tps_degradation_pct"),
             metrics["decode_tps_degradation_pct_max"], "max")
check_metric("thermal_headroom_sustained",
             report.get("thermal_headroom_sustained"),
             metrics["thermal_headroom_floor_sustained"], "floor")
check_metric("rss_growth_pct",
             report.get("rss_growth_pct"),
             metrics["rss_growth_pct_max"], "max")

print("STATUS=passed")
print("SUSTAINED_PERF_GATE_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "SUSTAINED_PERF_GATE_V1_SKIPPED=1"
  SUSTAINED_PERF_GATE_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

SUSTAINED_PERF_GATE_V1_OK=1
exit 0
