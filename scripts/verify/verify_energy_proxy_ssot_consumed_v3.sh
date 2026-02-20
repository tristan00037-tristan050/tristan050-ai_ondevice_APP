#!/usr/bin/env bash
set -euo pipefail

AI_ENERGY_PROXY_SSOT_RUNS_CONSUMED_OK=0
AI_ENERGY_PROXY_SSOT_MIN_P50_CONSUMED_OK=0

trap 'echo "AI_ENERGY_PROXY_SSOT_RUNS_CONSUMED_OK=$AI_ENERGY_PROXY_SSOT_RUNS_CONSUMED_OK";
      echo "AI_ENERGY_PROXY_SSOT_MIN_P50_CONSUMED_OK=$AI_ENERGY_PROXY_SSOT_MIN_P50_CONSUMED_OK"' EXIT

policy="docs/ops/contracts/ENERGY_PROXY_POLICY_V3.md"
measure="scripts/ai/energy_proxy_measure_v3.mjs"

test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "ENERGY_PROXY_POLICY_V3_TOKEN=1" "$policy" || { echo "BLOCK: missing token"; exit 1; }
test -f "$measure" || { echo "BLOCK: missing $measure"; exit 1; }

runs="$(grep -E '^MEASUREMENT_WINDOW_RUNS=' "$policy" | tail -n1 | cut -d= -f2)"
min_p50="$(grep -E '^MIN_P50_CPU_TIME_MS=' "$policy" | tail -n1 | cut -d= -f2)"
min_sum="$(grep -E '^MIN_SUM_CPU_TIME_MS=' "$policy" | tail -n1 | cut -d= -f2)"

[ -n "$runs" ] && [ -n "$min_p50" ] && [ -n "$min_sum" ] || { echo "BLOCK: missing SSOT fields"; exit 1; }

out="$(node "$measure" "$runs")"
echo "$out" | grep -q '"sample_count"' || { echo "BLOCK: bad measure output"; exit 1; }

sample_count="$(echo "$out" | node -e 'const x=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(String(x.sample_count))')"
p50="$(echo "$out" | node -e 'const x=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(String(x.p50_ms))')"
sum="$(echo "$out" | node -e 'const x=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(String(x.sum_ms))')"

# SSOT runs 소비 증명
[ "$sample_count" = "$runs" ] || { echo "BLOCK: runs not consumed (sample_count=$sample_count runs=$runs)"; exit 1; }

# SSOT 임계치 소비 증명 (float 비교)
awk -v a="$p50" -v b="$min_p50" 'BEGIN{exit (a>=b)?0:1}' || { echo "BLOCK: p50 below SSOT min"; exit 1; }
awk -v a="$sum" -v b="$min_sum" 'BEGIN{exit (a>=b)?0:1}' || { echo "BLOCK: sum below SSOT min"; exit 1; }

AI_ENERGY_PROXY_SSOT_RUNS_CONSUMED_OK=1
AI_ENERGY_PROXY_SSOT_MIN_P50_CONSUMED_OK=1
exit 0
