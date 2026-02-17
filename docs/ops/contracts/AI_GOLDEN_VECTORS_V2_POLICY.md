# AI GOLDEN VECTORS POLICY — v2 (SSOT)

Date: 2026-02-17
Status: DECIDED
Scope: AI golden vectors determinism and fingerprint validation

## Invariants
1) Golden vectors SSOT must exist and contain input/expected_output hash/seed/mode.
2) Determinism: identical input must produce identical fingerprint (fail-closed).
3) Fingerprint validation: output must match expected fingerprint from SSOT.

## Implementation SSOT
- SSOT: scripts/ai/golden_vectors_v2.json
- Library: scripts/ai/verify_golden_vectors_v2.cjs
- Verify gate: scripts/verify/verify_ai_golden_vectors_v2.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- AI_GOLDEN_VECTORS_V2_OK=1
- AI_DETERMINISM_FINGERPRINT_OK=1

## Token
AI_GOLDEN_VECTORS_V2_POLICY_TOKEN=1

