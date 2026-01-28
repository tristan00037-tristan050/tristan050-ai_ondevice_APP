# PROD Delivered Keyset — SEALED Record

This record permanently pins the PROD Delivered keyset and verification method (output-only) to prevent drift.

## Evidence
- Keyset SSOT PR: #253
- Verification command (output-only):
  - bash scripts/verify/verify_repo_contracts.sh ; echo EXIT=$?

## Required keyset (SSOT)
Source: docs/ops/contracts/PROD_DELIVERED_KEYS_SSOT.md

- POLICY_HEADERS_REQUIRED_OK=1
- POLICY_HEADERS_FAILCLOSED_OK=1

- META_ONLY_ALLOWLIST_ENFORCED_OK=1
- META_ONLY_VALIDATOR_PARITY_OK=1

- EXPORT_TWO_STEP_OK=1
- EXPORT_APPROVAL_AUDITED_OK=1
- EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=1
- EXPORT_APPROVE_AUDIT_V2_OK=1

- MOCK_NETWORK_ZERO_OK=1

- PERF_P95_BUDGET_DEFINED_OK=1
- PERF_P95_CONTRACT_OK=1
- PERF_P95_REGRESSION_BLOCK_OK=1
- PERF_P95_BASELINE_PINNED_OK=1

- TEST_EVENT_SELECTION_GUARD_OK=1

## DoD (output-based)
- PROD_DELIVERED_KEYSET_PRESENT_OK=1
- PROD_DELIVERED_KEYSET_GUARD_OK=1
- EXIT=0

SEALED rule
- placeholder/TODO 금지
- 출력 기반 증빙만 인정
