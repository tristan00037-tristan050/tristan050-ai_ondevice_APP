#!/usr/bin/env bash
set -euo pipefail

AI_ENERGY_PROXY_NORMALIZED_V2_OK=0
AI_ENERGY_PROXY_STABILITY_V2_OK=0

trap 'echo "AI_ENERGY_PROXY_NORMALIZED_V2_OK=${AI_ENERGY_PROXY_NORMALIZED_V2_OK}";
      echo "AI_ENERGY_PROXY_STABILITY_V2_OK=${AI_ENERGY_PROXY_STABILITY_V2_OK}"' EXIT

policy="docs/ops/contracts/ENERGY_PROXY_NORMALIZED_POLICY_V2.md"
impl="packages/common/budget/energy_proxy_cpu_time_ms_normalized_v2.cjs"
fx="scripts/ai/fixtures/energy_proxy_normalized_expected_v2.json"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "ENERGY_PROXY_NORMALIZED_POLICY_V2_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$impl" || { echo "BLOCK: missing impl"; exit 1; }
test -f "$fx" || { echo "BLOCK: missing expected fixture"; exit 1; }

node - <<'NODE'
'use strict';
const fs = require('fs');
const fx = JSON.parse(fs.readFileSync('scripts/ai/fixtures/energy_proxy_normalized_expected_v2.json','utf8'));
const { normalizedCpuTimeMsV2 } = require('./packages/common/budget/energy_proxy_cpu_time_ms_normalized_v2.cjs');

const out = normalizedCpuTimeMsV2(fx.usage_us, fx.inference_count);

if (!(out.cpu_time_ms > 0)) throw new Error('BLOCK: cpu_time_ms must be > 0');
if (!(out.normalized_cpu_time_ms > 0)) throw new Error('BLOCK: normalized_cpu_time_ms must be > 0');

if (out.cpu_time_ms < fx.expected.cpu_time_ms_min) throw new Error('BLOCK: cpu_time_ms below expected min');
if (out.normalized_cpu_time_ms < fx.expected.normalized_cpu_time_ms_min) throw new Error('BLOCK: normalized below expected min');

// Basic stability check: same input must produce identical outputs
const out2 = normalizedCpuTimeMsV2(fx.usage_us, fx.inference_count);
if (out.cpu_time_ms !== out2.cpu_time_ms) throw new Error('BLOCK: cpu_time_ms not stable');
if (out.normalized_cpu_time_ms !== out2.normalized_cpu_time_ms) throw new Error('BLOCK: normalized not stable');

console.log('OK');
NODE

AI_ENERGY_PROXY_NORMALIZED_V2_OK=1
AI_ENERGY_PROXY_STABILITY_V2_OK=1
exit 0
