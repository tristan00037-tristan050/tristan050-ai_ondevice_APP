# AI VARIANCE OUTLIER POLICY — v1 (SSOT)

Date: 2026-02-17
Status: DECIDED
Scope: AI performance variance and outlier detection

## Invariants
1) p50/p95 variance must not exceed upper bound (fail-closed).
2) Outlier ratio must not exceed upper bound (fail-closed).
3) Variance and outlier measurements must be computed from actual performance data.

## Implementation SSOT
- Library: scripts/ai/verify_variance_outlier_v1.cjs
- Verify gate: scripts/verify/verify_ai_variance_outlier_v1.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- AI_VARIANCE_OK=1
- AI_OUTLIER_RATIO_OK=1

## Token
AI_VARIANCE_OUTLIER_POLICY_V1_TOKEN=1

