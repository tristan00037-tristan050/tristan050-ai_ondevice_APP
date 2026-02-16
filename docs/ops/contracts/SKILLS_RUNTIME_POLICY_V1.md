# SKILLS RUNTIME POLICY — v1 (SSOT)

Date: 2026-02-15
Status: DECIDED
Scope: Skills runtime capability gating (manifest-based, fail-closed)

## Goal

Skills runtime escape = 0 by construction. Only capabilities declared in manifest are allowed.

## Invariants (must be enforced by code)

1) 매니페스트 외 capability는 BLOCK.
2) Skill ID must be registered in manifest.
3) Requested capabilities must be subset of manifest.capabilities.
4) Meta-only proof must be generated for all skill invocations (원문 0).

## Implementation SSOT

- Policy: `docs/ops/contracts/SKILLS_RUNTIME_POLICY_V1.md`
- Manifest: `scripts/agent/skills_manifest_v1.json`
- Library: `scripts/agent/skills_runtime_gate_v1.cjs`
- Self-test: `scripts/agent/skills_runtime_selftest_v1.cjs`
- Verify gate: `scripts/verify/verify_skills_runtime_v1.sh`
- Repo-wide gate wiring: `scripts/verify/verify_repo_contracts.sh`

## DoD Keys (printed by verify only)

- SKILLS_MANIFEST_PRESENT_OK=1
- SKILLS_CAPABILITY_GATE_BLOCK_OK=1
- SKILLS_META_ONLY_PROOF_OK=1

## Token

SKILLS_CAPABILITY_GATE_REQUIRED=1

