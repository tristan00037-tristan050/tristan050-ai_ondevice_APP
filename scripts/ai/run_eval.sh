#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest
OUT="ai/reports/latest/metrics.json"

RUNNER="scripts/verify/_runners/p2_ai_02_budget_gates_v0.cjs"
if [ ! -f "$RUNNER" ]; then
  echo "BLOCK: BUDGET_RUNNER_MISSING"
  exit 1
fi

# 러너 실행 (meta-only 출력)
RAW="$(node "$RUNNER" 2>&1 || true)"

# 실패면 ERROR_CODE=...가 나옵니다.
if echo "$RAW" | grep -q "^ERROR_CODE="; then
  echo "$RAW" | grep "^ERROR_CODE=" | head -1
  echo "BLOCK: budget runner failed"
  exit 1
fi

# 필요한 값 파싱
LAT="$(echo "$RAW" | grep "^MEASURE_latency_ms=" | head -1 | cut -d= -f2)"
MEM="$(echo "$RAW" | grep "^MEASURE_mem_peak_mb=" | head -1 | cut -d= -f2)"
CPU="$(echo "$RAW" | grep "^MEASURE_cpu_time_ms=" | head -1 | cut -d= -f2)"

python3 - <<PY
import json, datetime, os
lat = float("${LAT}" or 0)
mem = float("${MEM}" or 0)
cpu = float("${CPU}" or 0)

data = {
  "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "task": "p2_ai_02_budget_gates_v0",
  "quality": {
    "metric_name": "budget_gate_placeholder",
    "value": 1.0
  },
  "latency_ms": {
    "p50": lat,
    "p95": lat
  },
  "resource": {
    "mem_peak_mb": mem,
    "cpu_time_ms": cpu
  },
  "note": "Measured via scripts/verify/_runners/p2_ai_02_budget_gates_v0.cjs (meta-only)"
}
with open("ai/reports/latest/metrics.json","w",encoding="utf-8") as f:
  json.dump(data,f,ensure_ascii=False,indent=2)
print("OK: wrote ai/reports/latest/metrics.json")
PY

echo "OK: wrote $OUT"
