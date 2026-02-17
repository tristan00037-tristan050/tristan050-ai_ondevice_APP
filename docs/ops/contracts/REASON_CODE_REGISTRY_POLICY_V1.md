# REASON CODE REGISTRY POLICY — v1 (SSOT)

Date: 2026-02-17
Status: DECIDED
Scope: reason_code validation and single source

## Invariants
1) 미등록 reason_code BLOCK (unregistered reason_code must be blocked).
2) reason_code는 단일 소스(registry)에서만 허용.
3) registry 파일 경로: scripts/ops/reason_code_registry_v1.json

## Implementation SSOT
- Registry: scripts/ops/reason_code_registry_v1.json
- Library: scripts/agent/reason_code_gate_v1.cjs
- Self-test: scripts/agent/reason_code_gate_selftest_v1.cjs
- Verify gate: scripts/verify/verify_reason_code_registry_v1.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- REASON_CODE_REGISTRY_PRESENT_OK=1
- REASON_CODE_NOT_REGISTERED_BLOCK_OK=1
- REASON_CODE_SINGLE_SOURCE_OK=1

## Token
REASON_CODE_REGISTRY_POLICY_V1_TOKEN=1

