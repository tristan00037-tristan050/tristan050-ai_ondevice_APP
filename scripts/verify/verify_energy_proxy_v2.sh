#!/usr/bin/env bash
set -euo pipefail

# P5-AI-P0-03 energy proxy fail-open/close v2 (판정만)
AI_ENERGY_PROXY_MEASUREMENT_WINDOW_SSOT_OK=0
AI_ENERGY_PROXY_NONTRIVIAL_SUM_GT0_OK=0
AI_ENERGY_PROXY_P50_POSITIVE_OK=0
AI_ENERGY_PROXY_EXPECTED_REQUIRED_OK=0

trap 'echo "AI_ENERGY_PROXY_MEASUREMENT_WINDOW_SSOT_OK=${AI_ENERGY_PROXY_MEASUREMENT_WINDOW_SSOT_OK}"; echo "AI_ENERGY_PROXY_NONTRIVIAL_SUM_GT0_OK=${AI_ENERGY_PROXY_NONTRIVIAL_SUM_GT0_OK}"; echo "AI_ENERGY_PROXY_P50_POSITIVE_OK=${AI_ENERGY_PROXY_P50_POSITIVE_OK}"; echo "AI_ENERGY_PROXY_EXPECTED_REQUIRED_OK=${AI_ENERGY_PROXY_EXPECTED_REQUIRED_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1) Policy V2 (measurement window SSOT)
doc="docs/ops/contracts/ENERGY_PROXY_POLICY_V2.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "ENERGY_PROXY_POLICY_V2_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }
AI_ENERGY_PROXY_MEASUREMENT_WINDOW_SSOT_OK=1

# 2) Expected fixture required
expected_fixture="scripts/ai/fixtures/energy_proxy_expected_v2.json"
[ -f "$expected_fixture" ] || { echo "BLOCK: expected fixture missing"; exit 1; }
node -e "
const fs = require('fs');
const p = process.argv[1];
const j = JSON.parse(fs.readFileSync(p, 'utf8'));
if (!j.version || j.version !== 'v2') throw new Error('BLOCK: expected fixture invalid (version)');
" "$expected_fixture" || { echo "BLOCK: expected fixture invalid"; exit 1; }
AI_ENERGY_PROXY_EXPECTED_REQUIRED_OK=1

# 3) Skip-branch static detection: implementation must not contain skip or early return 0
impl="packages/common/budget/energy_proxy_cpu_time_ms_v2.cjs"
[ -f "$impl" ] || { echo "BLOCK: implementation missing"; exit 1; }
if grep -E '^\s*return\s+0\s*;' "$impl" >/dev/null 2>&1; then
  echo "BLOCK: skip branch (return 0) in implementation"
  exit 1
fi
if grep -qi '\bskip\b' "$impl" 2>/dev/null; then
  echo "BLOCK: skip branch detected in implementation"
  exit 1
fi
# Verify script must not bypass checks via SKIP
if grep -E '^\s*echo\s+[\"'"'"']SKIP' "$(dirname "$0")/verify_energy_proxy_v2.sh" 2>/dev/null | grep -v 'BLOCK:' >/dev/null 2>&1; then
  echo "BLOCK: skip branch in verify script"
  exit 1
fi

# 4) Run 10 times, sum and p50; p50<=0 or sum<=0 -> BLOCK
command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

node - <<'NODE'
const path = require("path");
const { cpuTimeMsV2 } = require("./packages/common/budget/energy_proxy_cpu_time_ms_v2.cjs");

function busy(ms) {
  const end = Date.now() + ms;
  let x = 0;
  while (Date.now() < end) x = (x * 1664525 + 1013904223) >>> 0;
  return x;
}

const deltas = [];
for (let i = 0; i < 10; i++) {
  const t0 = cpuTimeMsV2();
  busy(5);
  const t1 = cpuTimeMsV2();
  deltas.push(t1 - t0);
}

const sum = deltas.reduce((a, b) => a + b, 0);
if (sum <= 0) {
  console.error("BLOCK: 10-run sum <= 0 (nontrivial sum required)");
  process.exit(1);
}

const sorted = [...deltas].sort((a, b) => a - b);
const p50 = sorted.length % 2 === 1
  ? sorted[(sorted.length - 1) / 2]
  : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;

if (p50 <= 0) {
  console.error("BLOCK: p50 <= 0 (positive p50 required)");
  process.exit(1);
}

process.exit(0);
NODE

AI_ENERGY_PROXY_NONTRIVIAL_SUM_GT0_OK=1
AI_ENERGY_PROXY_P50_POSITIVE_OK=1
exit 0
