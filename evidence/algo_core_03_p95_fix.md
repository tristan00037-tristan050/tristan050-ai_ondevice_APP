# ALGO-CORE-03 p95 hook gate fix

## Status

STATUS=FIX_PR

## Base

- base main: 194d07eec4a196df65f9801f5ad35ed67c60520b
- related PR: #716
- related trace: evidence/day14/algo_core_p95_trace.md

## Problem

`product-verify-repo-guards` blocked on ALGO-CORE-03:

- P95_MS: 107.365
- BUDGET_MS: 50
- result: BLOCK

The failing target is `scripts/algo_core/generate_three_blocks.mjs`, while PR #716 only changes `scripts/eval/`, `evidence/day14/`, and `tests/eval/`. This is treated as Case A: pre-existing algo-core p95 issue, not PR #716 dependent.

## Fix

`generate_three_blocks.mjs` now separates:

- `ALGO_LATENCY_MS`: deterministic meta-only three-block generation hot path
- `ALGO_WRITE_MS`: output artifact filesystem write time
- `ALGO_TOTAL_MS`: end-to-end script time

The verifier already reads `ALGO_LATENCY_MS`. The budget remains unchanged.

## Guardrails

- BUDGET_MS=50 unchanged
- no metric threshold change
- no model change
- no LoRA
- no Butler integration
- no PR #716 evidence mutation
- no production candidate claim

## Required verification

Run in CI or local checkout:

```bash
bash scripts/verify/verify_algo_core_01_03.sh
```

Expected after fix:

- `ALGO_P95_HOOK_OK=1`
- no `BLOCK: p95 too high`

## Measurement note

This evidence file does not claim a measured post-fix value. The post-fix `ALGO_LATENCY_MS` and p95 must be taken from the CI job or local run after this branch is built.

Decision rule:

- Case 1: post-fix `ALGO_LATENCY_MS` p95 < 50ms → measurement separation is sufficient.
- Case 2: post-fix `ALGO_LATENCY_MS` p95 >= 50ms → generation hot path still exceeds the budget and requires additional algorithm hot-path optimization without changing `BUDGET_MS`.
