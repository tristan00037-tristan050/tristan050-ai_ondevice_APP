# PATH SCOPE POLICY — v1 (SSOT)

Date: 2026-02-17
Status: DECIDED
Scope: path scope validation and single source

## Invariants
1) Path scope SSOT must exist and be valid JSON.
2) SSOT must not contain placeholder values (fail-closed).
3) Actual path usage must match SSOT (drift=0).

## Implementation SSOT
- SSOT: docs/ops/contracts/PATH_SCOPE_SSOT_V1.json
- Verify gate: scripts/verify/verify_path_scope_ssot_v1.sh
- Repo-wide wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys
- PATH_SCOPE_SSOT_PRESENT_OK=1
- PATH_SCOPE_NO_PLACEHOLDER_OK=1
- PATH_SCOPE_DRIFT_0_OK=1

## Token
PATH_SCOPE_POLICY_V1_TOKEN=1

