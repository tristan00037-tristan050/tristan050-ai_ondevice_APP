#!/usr/bin/env bash
set -euo pipefail

AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=0
AI_AB_BENCH_RUNS_TIERED_V1_OK=0

trap 'echo "AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=${AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK}";
      echo "AI_AB_BENCH_RUNS_TIERED_V1_OK=${AI_AB_BENCH_RUNS_TIERED_V1_OK}"' EXIT

policy="docs/ops/contracts/AI_AB_BENCH_POLICY_V1.md"
workflow=".github/workflows/ai-ab-bench-nightly.yml"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "AI_AB_BENCH_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$workflow" || { echo "BLOCK: missing nightly workflow"; exit 1; }

# Extract numeric values (fail-closed if missing)
runs_pr="$(grep -E '^RUNS_PR=' "$policy" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"
runs_nightly="$(grep -E '^RUNS_NIGHTLY=' "$policy" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"

[[ "$runs_pr" =~ ^[0-9]+$ ]] || { echo "BLOCK: RUNS_PR invalid"; exit 1; }
[[ "$runs_nightly" =~ ^[0-9]+$ ]] || { echo "BLOCK: RUNS_NIGHTLY invalid"; exit 1; }

# Tiered enforcement: nightly must be strictly greater than PR
if [[ "$runs_nightly" -le "$runs_pr" ]]; then
  echo "BLOCK: RUNS_NIGHTLY must be > RUNS_PR"
  exit 1
fi

AI_NIGHTLY_WORKFLOW_PRESENT_V1_OK=1
AI_AB_BENCH_RUNS_TIERED_V1_OK=1
exit 0
