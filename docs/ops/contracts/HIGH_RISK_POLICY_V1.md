# HIGH RISK POLICY — v1 (SSOT)

Date: 2026-02-15
Status: DECIDED
Scope: High-risk operation approval gate + taint propagation

HIGH_RISK_APPROVAL_REQUIRED=1

## Goal
High-risk operations must be explicitly approved before execution.
Taint propagation ensures that unapproved high-risk state cannot be bypassed.

## Invariants (must be enforced by code)
1) HIGH risk level without approval → BLOCK
2) HIGH risk level with valid approval → ALLOW + taint=1
3) taint=1 state without approval → BLOCK (propagation check)
4) LOW/OK risk levels → ALLOW + taint=0 (no approval required)
5) Approval format must include: approval_token_sha256, approval_scope, approved_at_utc

## Taint Key
- TAINT_HIGH_RISK=1 (when high-risk operation is approved and executed)

## Approval Evidence Format
- approval_token_sha256: SHA256 hash of approval token
- approval_scope: Scope identifier (e.g., scope_hash)
- approved_at_utc: ISO 8601 timestamp (UTC)

## Implementation SSOT
- Library: scripts/agent/high_risk_gate_v1.cjs
- Self-test: scripts/agent/high_risk_gate_selftest_v1.cjs
- Verify gate: scripts/verify/verify_high_risk_gate_v1.sh
- Repo-wide gate wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys (printed by verify only)
- HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK=1
- HIGH_RISK_TAINT_PROPAGATION_OK=1
- HIGH_RISK_APPROVAL_FORMAT_OK=1

