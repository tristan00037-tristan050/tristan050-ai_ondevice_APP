#!/usr/bin/env bash
set -euo pipefail

AI_ENERGY_PROXY_POLICY_V1_OK=0
AI_ENERGY_PROXY_NONTRIVIAL_V1_OK=0
trap 'echo "AI_ENERGY_PROXY_POLICY_V1_OK=$AI_ENERGY_PROXY_POLICY_V1_OK"; echo "AI_ENERGY_PROXY_NONTRIVIAL_V1_OK=$AI_ENERGY_PROXY_NONTRIVIAL_V1_OK"' EXIT

doc="docs/ops/contracts/ENERGY_PROXY_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "ENERGY_PROXY_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }
AI_ENERGY_PROXY_POLICY_V1_OK=1

command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

node - <<'NODE'
const { cpuTimeMsV1 } = require("./packages/common/budget/energy_proxy_cpu_time_ms_v1.cjs");

function busy(ms) {
  const end = Date.now() + ms;
  let x = 0;
  while (Date.now() < end) x = (x * 1664525 + 1013904223) >>> 0;
  return x;
}

let nonZero = 0;

for (let i = 0; i < 10; i++) {
  const t0 = cpuTimeMsV1();
  busy(5); // 최소 측정 구간 확보
  const t1 = cpuTimeMsV1();
  const d = t1 - t0;
  if (d > 0) nonZero++;
}

if (nonZero === 0) {
  console.error("BLOCK: CPU_TIME_ALWAYS_ZERO_V1");
  process.exit(1);
}
process.exit(0);
NODE

AI_ENERGY_PROXY_NONTRIVIAL_V1_OK=1
exit 0

