#!/usr/bin/env bash
set -euo pipefail

AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=0
AI_AB_BENCH_RUNS_TIERED_V1_OK=0

trap 'echo "AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=${AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK}";
      echo "AI_AB_BENCH_RUNS_TIERED_V1_OK=${AI_AB_BENCH_RUNS_TIERED_V1_OK}"' EXIT

policy="docs/ops/contracts/AI_AB_BENCH_POLICY_V1.md"
nightly=".github/workflows/ai-ab-bench-nightly.yml"
prwf=".github/workflows/ai-ab-bench-gates.yml"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "AI_AB_BENCH_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$nightly" || { echo "BLOCK: missing nightly workflow"; exit 1; }
test -f "$prwf" || { echo "BLOCK: missing PR ab-bench workflow"; exit 1; }

# Parse policy (fail-closed)
runs_pr="$(grep -E '^RUNS_PR=' "$policy" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"
runs_nightly="$(grep -E '^RUNS_NIGHTLY=' "$policy" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"
warmup="$(grep -E '^WARMUP=' "$policy" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"

[[ "$runs_pr" =~ ^[0-9]+$ ]] || { echo "BLOCK: RUNS_PR invalid"; exit 1; }
[[ "$runs_nightly" =~ ^[0-9]+$ ]] || { echo "BLOCK: RUNS_NIGHTLY invalid"; exit 1; }
[[ "$warmup" =~ ^[0-9]+$ ]] || { echo "BLOCK: WARMUP invalid"; exit 1; }

# Tiered enforcement: nightly must be > PR
if [[ "$runs_nightly" -le "$runs_pr" ]]; then
  echo "BLOCK: RUNS_NIGHTLY must be > RUNS_PR"
  exit 1
fi

# P1 fix: nightly must actually run bench + gate
grep -Eq 'scripts/ai/run_ab_bench\.sh' "$nightly" || { echo "BLOCK: nightly does not run run_ab_bench.sh"; exit 1; }
grep -Eq 'scripts/ai/gate_ab_bench\.sh' "$nightly" || { echo "BLOCK: nightly does not run gate_ab_bench.sh"; exit 1; }

# P1 fix: nightly must consume policy to set RUNS (not hardcode)
grep -q 'RUNS_NIGHTLY=' "$nightly" || { echo "BLOCK: nightly does not read RUNS_NIGHTLY from policy"; exit 1; }
grep -q 'AI_AB_BENCH_POLICY_V1' "$nightly" || { echo "BLOCK: nightly does not reference policy"; exit 1; }
grep -Eq 'echo "RUNS=.*>>.*GITHUB_ENV' "$nightly" || { echo "BLOCK: nightly does not export RUNS from RUNS_NIGHTLY"; exit 1; }

# P1 fix: PR workflow RUNS/WARMUP must match policy values (prevents bypass)
grep -Eq "^[[:space:]]*RUNS:[[:space:]]*\"$runs_pr\"[[:space:]]*$" "$prwf" || { echo "BLOCK: PR workflow RUNS not equal to policy RUNS_PR"; exit 1; }
grep -Eq "^[[:space:]]*WARMUP:[[:space:]]*\"$warmup\"[[:space:]]*$" "$prwf" || { echo "BLOCK: PR workflow WARMUP not equal to policy WARMUP"; exit 1; }

AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=1
AI_AB_BENCH_RUNS_TIERED_V1_OK=1
exit 0
