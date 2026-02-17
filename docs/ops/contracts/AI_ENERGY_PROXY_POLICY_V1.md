# AI ENERGY PROXY POLICY — v1 (SSOT)

Date: 2026-02-17
Status: DECIDED
Scope: AI energy proxy definition and stability validation

## Invariants
1) Energy proxy is a single formula with inputs: latency_ms, mem_mb, steps (or tokens), device_class.
2) Measurements must be loaded from SSOT fixture file (fail-closed).
3) Stability: computed values must be within allowed tolerance (relative 5% or absolute threshold).
4) Variance/outlier: p95/p50 ratio must not exceed threshold.

## Implementation SSOT
- Policy: docs/ops/contracts/AI_ENERGY_PROXY_POLICY_V1.md
- Fixture: scripts/ai/fixtures/energy_proxy_measurements_v1.json
- Library: scripts/ai/energy_proxy_v1.cjs
- Verifier: scripts/ai/verify_energy_proxy_stability_v1.cjs
- Verify gate: scripts/verify/verify_ai_energy_proxy_v1.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1
- AI_ENERGY_MEASUREMENTS_SOURCE_OK=1
- AI_ENERGY_STABILITY_OK=1

## Token
AI_ENERGY_PROXY_POLICY_V1_TOKEN=1

