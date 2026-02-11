#!/usr/bin/env bash
set -euo pipefail

FILE="ai/reports/latest/ab_bench.json"
if [ ! -f "$FILE" ]; then
  echo "BLOCK: ab_bench.json missing (run scripts/ai/run_ab_bench.sh first)"
  exit 1
fi

# 기준선(필요시 환경변수로 조정)
A_P95_BUDGET_MS="${A_P95_BUDGET_MS:-5}"
B_P95_BUDGET_MS="${B_P95_BUDGET_MS:-5}"

python3 - <<PY
import json, sys
j=json.load(open("${FILE}","r",encoding="utf-8"))

A=float(j["A"]["latency_ms"]["p95"])
B=float(j["B"]["latency_ms"]["p95"])
stable=int(j.get("fingerprint_both_stable",0))

A_budget=float("${A_P95_BUDGET_MS}")
B_budget=float("${B_P95_BUDGET_MS}")

ok=True
if stable!=1:
  print("BLOCK: FINGERPRINT_BOTH_STABLE!=1")
  ok=False

if A > A_budget:
  print(f"BLOCK: A_P95_MS {A} > A_P95_BUDGET_MS {A_budget}")
  ok=False

if B > B_budget:
  print(f"BLOCK: B_P95_MS {B} > B_P95_BUDGET_MS {B_budget}")
  ok=False

if ok:
  print("AI_AB_BENCH_GATES_OK=1")
  sys.exit(0)
sys.exit(1)
PY
