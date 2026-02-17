# INSTRUCTION LAYERS POLICY — v1 (SSOT)

Date: 2026-02-16
Status: DECIDED
Scope: instruction layers storage/transmission

## Invariants
1) 원문 저장/전파 0 (raw text must never be persisted or emitted).
2) 출력/저장은 hash + scope_hash + layer_id + reason_code + ts_utc 같은 meta-only만 허용.
3) layer_id는 registry에 등록된 값만 허용(미등록은 BLOCK).

## Implementation SSOT
- Registry: scripts/agent/instruction_layers_registry_v1.json
- Library: scripts/agent/instruction_layers_v1.cjs
- Self-test: scripts/agent/instruction_layers_selftest_v1.cjs
- Verify gate: scripts/verify/verify_instruction_layers_v1.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- INSTRUCTION_RAW_0_OK=1
- INSTRUCTION_HASH_ONLY_OK=1
- INSTRUCTION_LAYER_REGISTRY_OK=1

## Token
INSTRUCTION_LAYERS_POLICY_V1_TOKEN=1

