#!/usr/bin/env bash
set -euo pipefail

AI_RESOURCE_BUDGET_LATENCY_OK=0
AI_RESOURCE_BUDGET_MEM_OK=0
AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=0
AI_BUDGET_MEASUREMENTS_PRESENT_OK=0
AI_ENERGY_PROXY_DEFINITION_SSOT_OK=0

cleanup() {
  echo "AI_RESOURCE_BUDGET_LATENCY_OK=${AI_RESOURCE_BUDGET_LATENCY_OK}"
  echo "AI_RESOURCE_BUDGET_MEM_OK=${AI_RESOURCE_BUDGET_MEM_OK}"
  echo "AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=${AI_RESOURCE_BUDGET_ENERGY_PROXY_OK}"
  echo "AI_BUDGET_MEASUREMENTS_PRESENT_OK=${AI_BUDGET_MEASUREMENTS_PRESENT_OK}"
  echo "AI_ENERGY_PROXY_DEFINITION_SSOT_OK=${AI_ENERGY_PROXY_DEFINITION_SSOT_OK}"
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# SSOT 존재 (fail-closed)
test -s "docs/ops/contracts/P2_AI_02_ENERGY_PROXY_SSOT_V1.md" || { echo "ERROR_CODE=ENERGY_PROXY_SSOT_MISSING"; exit 1; }
test -s "docs/ops/contracts/P2_AI_02_BUDGET_THRESHOLDS_V1.json" || { echo "ERROR_CODE=BUDGET_SSOT_MISSING"; exit 1; }
AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1

# Runner 실행(설치/다운로드 없음)
OUT="$(node scripts/verify/_runners/p2_ai_02_budget_gates_v0.cjs 2>/dev/null || true)"

# runner가 실패하면 ERROR_CODE만 출력하도록 설계됨
if echo "$OUT" | grep -q "^ERROR_CODE="; then
  echo "$OUT" | grep "^ERROR_CODE=" | head -1
  exit 1
fi

# 측정치 존재 확인(fail-closed)
LAT="$(echo "$OUT" | awk -F= '/^MEASURE_latency_ms=/{print $2}' | head -1)"
MEM="$(echo "$OUT" | awk -F= '/^MEASURE_mem_peak_mb=/{print $2}' | head -1)"
CPU="$(echo "$OUT" | awk -F= '/^MEASURE_cpu_time_ms=/{print $2}' | head -1)"

if [[ -z "${LAT}" || -z "${MEM}" || -z "${CPU}" ]]; then
  echo "ERROR_CODE=MEASUREMENT_MISSING"
  exit 1
fi

AI_BUDGET_MEASUREMENTS_PRESENT_OK=1
AI_RESOURCE_BUDGET_LATENCY_OK=1
AI_RESOURCE_BUDGET_MEM_OK=1
AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=1

# meta-only evidence passthrough
echo "$OUT" | grep -E '^(MEASURE_|BUDGET_)' || true

exit 0

