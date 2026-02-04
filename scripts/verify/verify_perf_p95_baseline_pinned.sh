#!/usr/bin/env bash
set -euo pipefail

PERF_P95_BASELINE_PINNED_OK=0
cleanup(){ echo "PERF_P95_BASELINE_PINNED_OK=${PERF_P95_BASELINE_PINNED_OK}"; }
trap cleanup EXIT

SSOT="docs/ops/contracts/PERF_P95_BUDGET_SSOT.json"
test -s "$SSOT"

node - <<'NODE'
const fs = require("fs");
const j = JSON.parse(fs.readFileSync("docs/ops/contracts/PERF_P95_BUDGET_SSOT.json","utf8"));

function block(msg){ console.error("BLOCK: " + msg); process.exit(1); }

if (!j.baseline_environment || typeof j.baseline_environment !== "object") block("baseline_environment must be an object");

for (const k of ["machine_class","os","browser","notes"]) {
  const v = j.baseline_environment[k];
  if (typeof v !== "string" || v.trim().length < 4) block(`baseline_environment.${k} must be non-empty`);
}

if (j.mode !== "mock") block("mode must be mock for the PERF_P95 gate SSOT");
if (typeof j.contract_ms !== "number" || j.contract_ms < 1) block("contract_ms must be a positive number");
if (typeof j.target_ms !== "number" || j.target_ms < 1) block("target_ms must be a positive number");
if (typeof j.samples !== "number" || j.samples < 10) block("samples must be >= 10");
if (typeof j.warmup !== "number" || j.warmup < 0) block("warmup must be >= 0");

process.stdout.write("OK\n");
NODE

echo "PERF_P95_BASELINE_PINNED_OK=1"
