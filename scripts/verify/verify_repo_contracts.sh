#!/usr/bin/env bash
set -euo pipefail

REPO_CONTRACTS_HYGIENE_OK=0
PRODUCT_VERIFY_WORKFLOW_TEMPLATE_OK=0
DOCS_NO_BANNED_PHRASES_OK=0
ONPREM_REAL_WORLD_PROOF_OK=0
ONPREM_REAL_WORLD_PROOF_FORMAT_OK=0
ONPREM_PROOF_LATEST_PRESENT_OK=0
ONPREM_PROOF_ARCHIVE_LINKED_OK=0
ONPREM_PROOF_SENSITIVE_SCAN_OK=0
ONPREM_PROOF_LATEST_FRESH_OK=0

OK_CONTAMINATION_REPO_GUARD_OK=0
REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=0
SSOT_PLACEHOLDER_GUARD_OK=0
REQUIRED_CHECK_NAME_STABILITY_OK=0
REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=0
NO_LOG_GREP_VERDICT_OK=0
NO_NPM_INSTALL_FALLBACK_OK=0
CANONICALIZE_SHARED_SINGLE_SOURCE_OK=0
TEST_EVENT_SELECTION_GUARD_OK=0

# New (H3.4-prep)
LOCKFILES_TRACKED_OK=0
REQUIRED_CHECK_CONTEXT_SINGLE_OK=0
AUDIT_APPEND_NO_DRIFT_OK=0
COUNTERS_NO_DRIFT_OK=0
ARTIFACTS_NOT_TRACKED_OK=0
REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=0

# PROD-02
POLICY_HEADERS_REQUIRED_OK=0
POLICY_HEADERS_FAILCLOSED_OK=0

# PROD-03
META_ONLY_ALLOWLIST_ENFORCED_OK=0
META_ONLY_VALIDATOR_PARITY_OK=0

# Track A-2
META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=0
META_ONLY_VALIDATOR_NO_DUPLICATION_OK=0
META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=0

# PROD-04
EXPORT_TWO_STEP_OK=0
EXPORT_APPROVAL_AUDITED_OK=0
EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=0
EXPORT_APPROVE_AUDIT_V2_OK=0

# PROD-05
MOCK_NETWORK_ZERO_OK=0

# PROD-DELIVERED (SSOT)
PROD_DELIVERED_KEYSET_PRESENT_OK=0
PROD_DELIVERED_KEYSET_GUARD_OK=0

# WEB-UX-01
WEB_E2E_MODE_SWITCH_WIRED_OK=0
WEB_E2E_MOCK_NETWORK_ZERO_OK=0
WEB_E2E_LIVE_HEADER_BUNDLE_OK=0

# WEB-UX-03
WEB_E2E_EXPORT_TWO_STEP_OK=0
WEB_E2E_EXPORT_AUDITV2_OK=0
EXPORT_APPROVE_IDEMPOTENT_OK=0
EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=0

# WEB-UX-04
PERF_E2E_EVENT_MARKS_WIRED_OK=0
PERF_E2E_MARKS_PARITY_OK=0

# PERF-REAL-PIPELINE
PERF_REAL_PIPELINE_WIRED_OK=0
PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=0
PERF_REAL_PIPELINE_NO_RAW_OK=0
PERF_REAL_PIPELINE_P95_BUDGET_OK=0
PERF_REAL_PIPELINE_MIN_SAMPLES_OK=0
PERF_REAL_PIPELINE_VARIANCE_OK=0

# WEB-UX-08
WEB_META_ONLY_NEGATIVE_SUITE_OK=0

# VERIFY-PURITY
VERIFY_PURITY_NO_INSTALL_OK=0
VERIFY_PURITY_FULL_SCOPE_OK=0
VERIFY_PURITY_ALLOWLIST_SSOT_OK=0

# P3-PREP-00 (Common Hardening)
VERIFY_NO_DEV_TCP_IN_VERIFY_OK=0
VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=0

# P3-PLAT-01 (Workflow Preflight SSOT)
WORKFLOW_PREFLIGHT_PRESENT_OK=0

# P3-PLAT-02 (Runtime Guard Helpers)
RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=0

# RUNTIME-EGRESS-ENV
RUNTIME_EGRESS_ENV_TEMPLATE_OK=0
RUNTIME_EGRESS_ENV_PROOF_OK=0

# MODEL-PACK-V0
MODEL_PACK_SCHEMA_SSOT_OK=0
MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=0
MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=0
MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=0
MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=0
MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=0
MODEL_PACK_V0_EXPIRES_ENFORCED_OK=0
MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=0
MODEL_PACK_V0_COMPAT_ENFORCED_OK=0

# ONDEVICE-MODEL-EXEC-V0 (Track B-1)
ONDEVICE_MODEL_EXEC_V0_OK=0
MODEL_PACK_VERIFY_REQUIRED_OK=0
ONDEVICE_EGRESS_DENY_PROOF_OK=0
ONDEVICE_NO_RAW_STORAGE_OK=0

# ONDEVICE-REAL-COMPUTE-ONCE (Track B-1.1)
ONDEVICE_REAL_COMPUTE_ONCE_OK=0
ONDEVICE_RESULT_FINGERPRINT_OK=0
ONDEVICE_COMPUTE_PATH_ONDEVICE_OK=0

# P2-AI-01
ONDEVICE_MODEL_PACK_LOADED_OK=0
ONDEVICE_MODEL_PACK_IDENTITY_OK=0
ONDEVICE_INFERENCE_ONCE_OK=0
ONDEVICE_OUTPUT_FINGERPRINT_OK=0
ONDEVICE_INFER_USES_PACK_PARAMS_OK=0

# AI-V1-MODULES
AI_PERF_HARNESS_V1_OK=0
AI_RERANK_NEARTIE_V1_OK=0
AI_CALIB_V1_OK=0
AI_PROPENSITY_IPS_SNIPS_V1_OK=0
AI_DETERMINISM_OK=0
AI_P95_BUDGET_OK=0
AI_NEARTIE_SWAP_BUDGET_OK=0

# P2-AI-02 (Budget Gates)
AI_RESOURCE_BUDGET_LATENCY_OK=0
AI_RESOURCE_BUDGET_MEM_OK=0
AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=0
AI_BUDGET_MEASUREMENTS_PRESENT_OK=0
AI_ENERGY_PROXY_DEFINITION_SSOT_OK=0

# ALGO-DETERMINISM-GATE
ALGO_DETERMINISM_VERIFIED_OK=0
ALGO_DETERMINISM_HASH_MATCH_OK=0
ALGO_DETERMINISM_MODE_REPORTED_OK=0

# OPS-HUB-V0
OPS_HUB_META_SCHEMA_SSOT_OK=0
OPS_HUB_NO_RAW_TEXT_GUARD_OK=0
OPS_HUB_REPORT_V0_OK=0
OPS_HUB_REPORT_INPUT_META_ONLY_OK=0
OPS_HUB_TRACEABILITY_OK=0
OPS_HUB_TRACEABILITY_REPORT_OK=0
OPS_HUB_TRACEABILITY_NO_RAW_OK=0
OPS_HUB_TRACE_REALPATH_PERSISTED_OK=0
OPS_HUB_TRACE_REALPATH_JOINABLE_OK=0
OPS_HUB_TRACE_REALPATH_NO_RAW_OK=0
OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=0

# OPS-HUB-TRACE-SERVICE-STORE
OPS_HUB_TRACE_SERVICE_PERSIST_OK=0
OPS_HUB_TRACE_IDEMPOTENT_OK=0
OPS_HUB_TRACE_NO_RAW_OK=0
OPS_HUB_TRACE_JOINABLE_OK=0

# A-3.1: Trace Security Lockdown
OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=0

# P1-PLAT-01
OPS_HUB_TRACE_DB_SCHEMA_OK=0
OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=0
OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=0
OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=0
OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=0

# REASON-CODES-V1
REASON_CODE_SINGLE_SOURCE_OK=0
REASON_CODE_DRIFT_GUARD_OK=0

# M6-SEALED-RECORD
M6_SEALED_RECORD_PRESENT_OK=0
M6_SEALED_RECORD_NO_PLACEHOLDER_OK=0
M6_SEALED_RECORD_PR_MAP_OK=0

# M7-SEALED-RECORD
M7_SEALED_RECORD_PRESENT_OK=0
M7_SEALED_RECORD_FORMAT_OK=0
M7_SEALED_RECORD_NO_PLACEHOLDER_OK=0

# ALGO-APPLY-E2E
ALGO_APPLY_FAILCLOSED_E2E_OK=0
ALGO_APPLY_STATE_UNCHANGED_OK=0
ALGO_APPLY_REASON_CODE_PRESERVED_OK=0
# BUTLER-RUNTIME-V0
RUNTIME_V0_HTTP_OK=0
RUNTIME_EGRESS_DENY_DEFAULT_OK=0
RUNTIME_SHADOW_ENDPOINT_OK=0
RUNTIME_SHADOW_HEADERS_OK=0
BFF_SHADOW_FIREFORGET_OK=0
RUNTIME_SHADOW_PROOF_OK=0

# BUTLER-SSOT
BUTLER_SSOT_V1_1_OK=0

# ALGO-CORE-GATEWAY-DOC
ALGO_CORE_GATEWAY_DEPLOY_DOC_OK=0

# ALGO-CORE-06
ALGO_CORE_PROD_SSOT_PRESENT_OK=0
ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=0
ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=0
ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=0
# ALGO-CORE-04
ALGO_CORE_RUNTIME_ROUTE_PRESENT_OK=0
ALGO_CORE_RUNTIME_PROD_FAILCLOSED_KEYS_OK=0

# ALGO-CORE-01~03
ALGO_META_ONLY_FAILCLOSED_OK=0
ALGO_THREE_BLOCKS_NO_RAW_OK=0
ALGO_SIGNED_MANIFEST_VERIFY_OK=0
ALGO_P95_HOOK_OK=0
ALGO_CORE_DELIVERED_KEYSET_PRESENT_OK=0
ALGO_CORE_DELIVERED_KEYSET_GUARD_OK=0

# PERF-01
PERF_P95_BUDGET_DEFINED_OK=0
PERF_P95_CONTRACT_OK=0
PERF_P95_REGRESSION_BLOCK_OK=0
PERF_P95_BASELINE_PINNED_OK=0

# ONPREM-01
ONPREM_COMPOSE_ASSETS_OK=0

# ONPREM-02
ONPREM_HELM_SKELETON_OK=0
ONPREM_HELM_SECRETS_GUARD_OK=0
ONPREM_HELM_TEMPLATE_SMOKE_OK=0
ONPREM_HELM_TEMPLATE_SECRET_REF_OK=0

# ONPREM-03/04 (Delivered keyset wiring)
ONPREM_SIGNED_BUNDLE_OK=0
ONPREM_INSTALL_VERIFY_OK=0

# ONPREM-06
ONPREM_SIGNING_KEY_REQUIRED_OK=0
ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=0
ONPREM_KEY_ID_ALLOWLIST_OK=0

# ONPREM-08
ONPREM_DELIVERED_KEYSET_PRESENT_OK=0
ONPREM_DELIVERED_KEYSET_GUARD_OK=0

cleanup(){
  echo "REPO_CONTRACTS_HYGIENE_OK=${REPO_CONTRACTS_HYGIENE_OK}"
  echo "PRODUCT_VERIFY_WORKFLOW_TEMPLATE_OK=${PRODUCT_VERIFY_WORKFLOW_TEMPLATE_OK}"
  echo "DOCS_NO_BANNED_PHRASES_OK=${DOCS_NO_BANNED_PHRASES_OK}"
  echo "ONPREM_REAL_WORLD_PROOF_OK=${ONPREM_REAL_WORLD_PROOF_OK}"
  echo "ONPREM_REAL_WORLD_PROOF_FORMAT_OK=${ONPREM_REAL_WORLD_PROOF_FORMAT_OK}"
  echo "ONPREM_PROOF_LATEST_PRESENT_OK=${ONPREM_PROOF_LATEST_PRESENT_OK}"
  echo "ONPREM_PROOF_ARCHIVE_LINKED_OK=${ONPREM_PROOF_ARCHIVE_LINKED_OK}"
  echo "ONPREM_PROOF_SENSITIVE_SCAN_OK=${ONPREM_PROOF_SENSITIVE_SCAN_OK}"
  echo "ONPREM_PROOF_LATEST_FRESH_OK=${ONPREM_PROOF_LATEST_FRESH_OK}"
  echo "OK_CONTAMINATION_REPO_GUARD_OK=${OK_CONTAMINATION_REPO_GUARD_OK}"
  echo "REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=${REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK}"
  echo "SSOT_PLACEHOLDER_GUARD_OK=${SSOT_PLACEHOLDER_GUARD_OK}"
  echo "REQUIRED_CHECK_NAME_STABILITY_OK=${REQUIRED_CHECK_NAME_STABILITY_OK}"
  echo "REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=${REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK}"
  echo "NO_LOG_GREP_VERDICT_OK=${NO_LOG_GREP_VERDICT_OK}"
  echo "NO_NPM_INSTALL_FALLBACK_OK=${NO_NPM_INSTALL_FALLBACK_OK}"
  echo "CANONICALIZE_SHARED_SINGLE_SOURCE_OK=${CANONICALIZE_SHARED_SINGLE_SOURCE_OK}"

  echo "LOCKFILES_TRACKED_OK=${LOCKFILES_TRACKED_OK}"
  echo "REQUIRED_CHECK_CONTEXT_SINGLE_OK=${REQUIRED_CHECK_CONTEXT_SINGLE_OK}"
  echo "AUDIT_APPEND_NO_DRIFT_OK=${AUDIT_APPEND_NO_DRIFT_OK}"
  echo "COUNTERS_NO_DRIFT_OK=${COUNTERS_NO_DRIFT_OK}"
  echo "ARTIFACTS_NOT_TRACKED_OK=${ARTIFACTS_NOT_TRACKED_OK}"
  echo "REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=${REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK}"

  echo "POLICY_HEADERS_REQUIRED_OK=${POLICY_HEADERS_REQUIRED_OK}"
  echo "POLICY_HEADERS_FAILCLOSED_OK=${POLICY_HEADERS_FAILCLOSED_OK}"

  echo "META_ONLY_ALLOWLIST_ENFORCED_OK=${META_ONLY_ALLOWLIST_ENFORCED_OK}"
  echo "META_ONLY_VALIDATOR_PARITY_OK=${META_ONLY_VALIDATOR_PARITY_OK}"
  echo "META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=${META_ONLY_VALIDATOR_SINGLE_SOURCE_OK}"
  echo "META_ONLY_VALIDATOR_NO_DUPLICATION_OK=${META_ONLY_VALIDATOR_NO_DUPLICATION_OK}"
  echo "META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=${META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK}"

  echo "EXPORT_TWO_STEP_OK=${EXPORT_TWO_STEP_OK}"
  echo "EXPORT_APPROVAL_AUDITED_OK=${EXPORT_APPROVAL_AUDITED_OK}"
  echo "EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=${EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK}"
  echo "EXPORT_APPROVE_AUDIT_V2_OK=${EXPORT_APPROVE_AUDIT_V2_OK}"

  echo "MOCK_NETWORK_ZERO_OK=${MOCK_NETWORK_ZERO_OK}"

  echo "PROD_DELIVERED_KEYSET_PRESENT_OK=${PROD_DELIVERED_KEYSET_PRESENT_OK}"
  echo "PROD_DELIVERED_KEYSET_GUARD_OK=${PROD_DELIVERED_KEYSET_GUARD_OK}"

  echo "PERF_P95_BUDGET_DEFINED_OK=${PERF_P95_BUDGET_DEFINED_OK}"
  echo "PERF_P95_CONTRACT_OK=${PERF_P95_CONTRACT_OK}"
  echo "PERF_P95_REGRESSION_BLOCK_OK=${PERF_P95_REGRESSION_BLOCK_OK}"
  echo "PERF_P95_BASELINE_PINNED_OK=${PERF_P95_BASELINE_PINNED_OK}"

  echo "ONPREM_COMPOSE_ASSETS_OK=${ONPREM_COMPOSE_ASSETS_OK}"

  echo "ONPREM_HELM_SKELETON_OK=${ONPREM_HELM_SKELETON_OK}"
  echo "ONPREM_HELM_SECRETS_GUARD_OK=${ONPREM_HELM_SECRETS_GUARD_OK}"
  echo "ONPREM_HELM_TEMPLATE_SMOKE_OK=${ONPREM_HELM_TEMPLATE_SMOKE_OK}"
  echo "ONPREM_HELM_TEMPLATE_SECRET_REF_OK=${ONPREM_HELM_TEMPLATE_SECRET_REF_OK}"

  echo "ONPREM_SIGNED_BUNDLE_OK=${ONPREM_SIGNED_BUNDLE_OK}"
  echo "ONPREM_INSTALL_VERIFY_OK=${ONPREM_INSTALL_VERIFY_OK}"

  echo "ONPREM_SIGNING_KEY_REQUIRED_OK=${ONPREM_SIGNING_KEY_REQUIRED_OK}"
  echo "ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=${ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK}"
  echo "ONPREM_KEY_ID_ALLOWLIST_OK=${ONPREM_KEY_ID_ALLOWLIST_OK}"

  echo "ONPREM_DELIVERED_KEYSET_PRESENT_OK=${ONPREM_DELIVERED_KEYSET_PRESENT_OK}"
  echo "ONPREM_DELIVERED_KEYSET_GUARD_OK=${ONPREM_DELIVERED_KEYSET_GUARD_OK}"

  echo "TEST_EVENT_SELECTION_GUARD_OK=${TEST_EVENT_SELECTION_GUARD_OK}"

  echo "PROD_DELIVERED_KEYSET_PRESENT_OK=${PROD_DELIVERED_KEYSET_PRESENT_OK}"
  echo "PROD_DELIVERED_KEYSET_GUARD_OK=${PROD_DELIVERED_KEYSET_GUARD_OK}"

  echo "WEB_E2E_MODE_SWITCH_WIRED_OK=${WEB_E2E_MODE_SWITCH_WIRED_OK}"
  echo "WEB_E2E_MOCK_NETWORK_ZERO_OK=${WEB_E2E_MOCK_NETWORK_ZERO_OK}"
  echo "WEB_E2E_LIVE_HEADER_BUNDLE_OK=${WEB_E2E_LIVE_HEADER_BUNDLE_OK}"
  echo "WEB_E2E_EXPORT_TWO_STEP_OK=${WEB_E2E_EXPORT_TWO_STEP_OK}"
  echo "WEB_E2E_EXPORT_AUDITV2_OK=${WEB_E2E_EXPORT_AUDITV2_OK}"
  echo "EXPORT_APPROVE_IDEMPOTENT_OK=${EXPORT_APPROVE_IDEMPOTENT_OK}"
  echo "EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=${EXPORT_APPROVE_AUDIT_ID_RETURNED_OK}"
  echo "PERF_E2E_EVENT_MARKS_WIRED_OK=${PERF_E2E_EVENT_MARKS_WIRED_OK}"
  echo "PERF_E2E_MARKS_PARITY_OK=${PERF_E2E_MARKS_PARITY_OK}"
  echo "PERF_REAL_PIPELINE_WIRED_OK=${PERF_REAL_PIPELINE_WIRED_OK}"
  echo "PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=${PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK}"
  echo "PERF_REAL_PIPELINE_NO_RAW_OK=${PERF_REAL_PIPELINE_NO_RAW_OK}"
  echo "PERF_REAL_PIPELINE_P95_BUDGET_OK=${PERF_REAL_PIPELINE_P95_BUDGET_OK}"
  echo "PERF_REAL_PIPELINE_MIN_SAMPLES_OK=${PERF_REAL_PIPELINE_MIN_SAMPLES_OK}"
  echo "PERF_REAL_PIPELINE_VARIANCE_OK=${PERF_REAL_PIPELINE_VARIANCE_OK}"
  echo "WEB_META_ONLY_NEGATIVE_SUITE_OK=${WEB_META_ONLY_NEGATIVE_SUITE_OK}"
  echo "VERIFY_PURITY_NO_INSTALL_OK=${VERIFY_PURITY_NO_INSTALL_OK}"
  echo "VERIFY_PURITY_FULL_SCOPE_OK=${VERIFY_PURITY_FULL_SCOPE_OK}"
  echo "VERIFY_PURITY_ALLOWLIST_SSOT_OK=${VERIFY_PURITY_ALLOWLIST_SSOT_OK}"

  # P3-PREP-00 (Common Hardening)
  echo "VERIFY_NO_DEV_TCP_IN_VERIFY_OK=${VERIFY_NO_DEV_TCP_IN_VERIFY_OK}"
  echo "VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=${VERIFY_RIPGREP_GUARD_PRESENT_V1_OK}"

  # P3-PLAT-01 (Workflow Preflight SSOT)
  echo "WORKFLOW_PREFLIGHT_PRESENT_OK=${WORKFLOW_PREFLIGHT_PRESENT_OK}"

  # P3-PLAT-02 (Runtime Guard Helpers)
  echo "RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=${RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK}"

  echo "RUNTIME_EGRESS_ENV_TEMPLATE_OK=${RUNTIME_EGRESS_ENV_TEMPLATE_OK}"
  echo "RUNTIME_EGRESS_ENV_PROOF_OK=${RUNTIME_EGRESS_ENV_PROOF_OK}"

  # MODEL-PACK-V0
  echo "MODEL_PACK_SCHEMA_SSOT_OK=${MODEL_PACK_SCHEMA_SSOT_OK}"
  echo "MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=${MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK}"
  echo "MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=${MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK}"
  echo "MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=${MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK}"
  echo "MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=${MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK}"
  echo "MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=${MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK}"
  echo "MODEL_PACK_V0_EXPIRES_ENFORCED_OK=${MODEL_PACK_V0_EXPIRES_ENFORCED_OK}"
  echo "MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=${MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK}"
  echo "MODEL_PACK_V0_COMPAT_ENFORCED_OK=${MODEL_PACK_V0_COMPAT_ENFORCED_OK}"

  # ONDEVICE-MODEL-EXEC-V0 (Track B-1)
  echo "ONDEVICE_MODEL_EXEC_V0_OK=${ONDEVICE_MODEL_EXEC_V0_OK}"
  echo "MODEL_PACK_VERIFY_REQUIRED_OK=${MODEL_PACK_VERIFY_REQUIRED_OK}"
  echo "ONDEVICE_EGRESS_DENY_PROOF_OK=${ONDEVICE_EGRESS_DENY_PROOF_OK}"
  echo "ONDEVICE_NO_RAW_STORAGE_OK=${ONDEVICE_NO_RAW_STORAGE_OK}"

  # ONDEVICE-REAL-COMPUTE-ONCE (Track B-1.1)
  echo "ONDEVICE_REAL_COMPUTE_ONCE_OK=${ONDEVICE_REAL_COMPUTE_ONCE_OK}"
  echo "ONDEVICE_RESULT_FINGERPRINT_OK=${ONDEVICE_RESULT_FINGERPRINT_OK}"
  echo "ONDEVICE_COMPUTE_PATH_ONDEVICE_OK=${ONDEVICE_COMPUTE_PATH_ONDEVICE_OK}"

  # P2-AI-01
  echo "ONDEVICE_MODEL_PACK_LOADED_OK=${ONDEVICE_MODEL_PACK_LOADED_OK}"
  echo "ONDEVICE_MODEL_PACK_IDENTITY_OK=${ONDEVICE_MODEL_PACK_IDENTITY_OK}"
  echo "ONDEVICE_INFERENCE_ONCE_OK=${ONDEVICE_INFERENCE_ONCE_OK}"
  echo "ONDEVICE_OUTPUT_FINGERPRINT_OK=${ONDEVICE_OUTPUT_FINGERPRINT_OK}"
  echo "ONDEVICE_INFER_USES_PACK_PARAMS_OK=${ONDEVICE_INFER_USES_PACK_PARAMS_OK}"

  # AI-V1-MODULES
  echo "AI_PERF_HARNESS_V1_OK=${AI_PERF_HARNESS_V1_OK}"
  echo "AI_RERANK_NEARTIE_V1_OK=${AI_RERANK_NEARTIE_V1_OK}"
  echo "AI_CALIB_V1_OK=${AI_CALIB_V1_OK}"
  echo "AI_PROPENSITY_IPS_SNIPS_V1_OK=${AI_PROPENSITY_IPS_SNIPS_V1_OK}"
  echo "AI_DETERMINISM_OK=${AI_DETERMINISM_OK}"
  echo "AI_P95_BUDGET_OK=${AI_P95_BUDGET_OK}"
  echo "AI_NEARTIE_SWAP_BUDGET_OK=${AI_NEARTIE_SWAP_BUDGET_OK}"

  # P2-AI-02 (Budget Gates)
  echo "AI_RESOURCE_BUDGET_LATENCY_OK=${AI_RESOURCE_BUDGET_LATENCY_OK}"
  echo "AI_RESOURCE_BUDGET_MEM_OK=${AI_RESOURCE_BUDGET_MEM_OK}"
  echo "AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=${AI_RESOURCE_BUDGET_ENERGY_PROXY_OK}"
  echo "AI_BUDGET_MEASUREMENTS_PRESENT_OK=${AI_BUDGET_MEASUREMENTS_PRESENT_OK}"
  echo "AI_ENERGY_PROXY_DEFINITION_SSOT_OK=${AI_ENERGY_PROXY_DEFINITION_SSOT_OK}"

  # ALGO-DETERMINISM-GATE
  echo "ALGO_DETERMINISM_VERIFIED_OK=${ALGO_DETERMINISM_VERIFIED_OK}"
  echo "ALGO_DETERMINISM_HASH_MATCH_OK=${ALGO_DETERMINISM_HASH_MATCH_OK}"
  echo "ALGO_DETERMINISM_MODE_REPORTED_OK=${ALGO_DETERMINISM_MODE_REPORTED_OK}"

  # OPS-HUB-V0
  echo "OPS_HUB_META_SCHEMA_SSOT_OK=${OPS_HUB_META_SCHEMA_SSOT_OK}"
  echo "OPS_HUB_NO_RAW_TEXT_GUARD_OK=${OPS_HUB_NO_RAW_TEXT_GUARD_OK}"
  echo "OPS_HUB_REPORT_V0_OK=${OPS_HUB_REPORT_V0_OK}"
  echo "OPS_HUB_REPORT_INPUT_META_ONLY_OK=${OPS_HUB_REPORT_INPUT_META_ONLY_OK}"
  echo "OPS_HUB_TRACEABILITY_OK=${OPS_HUB_TRACEABILITY_OK}"
  echo "OPS_HUB_TRACEABILITY_REPORT_OK=${OPS_HUB_TRACEABILITY_REPORT_OK}"
  echo "OPS_HUB_TRACEABILITY_NO_RAW_OK=${OPS_HUB_TRACEABILITY_NO_RAW_OK}"
  echo "OPS_HUB_TRACE_REALPATH_PERSISTED_OK=${OPS_HUB_TRACE_REALPATH_PERSISTED_OK}"
  echo "OPS_HUB_TRACE_REALPATH_JOINABLE_OK=${OPS_HUB_TRACE_REALPATH_JOINABLE_OK}"
  echo "OPS_HUB_TRACE_REALPATH_NO_RAW_OK=${OPS_HUB_TRACE_REALPATH_NO_RAW_OK}"
  echo "OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=${OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK}"

  # OPS-HUB-TRACE-SERVICE-STORE
  echo "OPS_HUB_TRACE_SERVICE_PERSIST_OK=${OPS_HUB_TRACE_SERVICE_PERSIST_OK}"
  echo "OPS_HUB_TRACE_IDEMPOTENT_OK=${OPS_HUB_TRACE_IDEMPOTENT_OK}"
  echo "OPS_HUB_TRACE_NO_RAW_OK=${OPS_HUB_TRACE_NO_RAW_OK}"
  echo "OPS_HUB_TRACE_JOINABLE_OK=${OPS_HUB_TRACE_JOINABLE_OK}"

  # A-3.1: Trace Security Lockdown
  echo "OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=${OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK}"

  # P1-PLAT-01: Trace DB Store
  echo "OPS_HUB_TRACE_DB_SCHEMA_OK=${OPS_HUB_TRACE_DB_SCHEMA_OK}"
  echo "OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=${OPS_HUB_TRACE_REQUEST_ID_INDEX_OK}"
  echo "OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=${OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK}"
  echo "OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=${OPS_HUB_TRACE_CONCURRENCY_SAFE_OK}"
  echo "OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=${OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK}"

  # REASON-CODES-V1
  echo "REASON_CODE_SINGLE_SOURCE_OK=${REASON_CODE_SINGLE_SOURCE_OK}"
  echo "REASON_CODE_DRIFT_GUARD_OK=${REASON_CODE_DRIFT_GUARD_OK}"

  # M6-SEALED-RECORD
  echo "M6_SEALED_RECORD_PRESENT_OK=${M6_SEALED_RECORD_PRESENT_OK}"
  echo "M6_SEALED_RECORD_NO_PLACEHOLDER_OK=${M6_SEALED_RECORD_NO_PLACEHOLDER_OK}"
  echo "M6_SEALED_RECORD_PR_MAP_OK=${M6_SEALED_RECORD_PR_MAP_OK}"

  # M7-SEALED-RECORD
  echo "M7_SEALED_RECORD_PRESENT_OK=${M7_SEALED_RECORD_PRESENT_OK}"
  echo "M7_SEALED_RECORD_FORMAT_OK=${M7_SEALED_RECORD_FORMAT_OK}"
  echo "M7_SEALED_RECORD_NO_PLACEHOLDER_OK=${M7_SEALED_RECORD_NO_PLACEHOLDER_OK}"

  # ALGO-APPLY-E2E
  echo "ALGO_APPLY_FAILCLOSED_E2E_OK=${ALGO_APPLY_FAILCLOSED_E2E_OK}"
  echo "ALGO_APPLY_STATE_UNCHANGED_OK=${ALGO_APPLY_STATE_UNCHANGED_OK}"
  echo "ALGO_APPLY_REASON_CODE_PRESERVED_OK=${ALGO_APPLY_REASON_CODE_PRESERVED_OK}"
  # BUTLER-RUNTIME-V0
  echo "RUNTIME_V0_HTTP_OK=${RUNTIME_V0_HTTP_OK}"
  echo "RUNTIME_EGRESS_DENY_DEFAULT_OK=${RUNTIME_EGRESS_DENY_DEFAULT_OK}"
  echo "RUNTIME_SHADOW_ENDPOINT_OK=${RUNTIME_SHADOW_ENDPOINT_OK}"
  echo "RUNTIME_SHADOW_HEADERS_OK=${RUNTIME_SHADOW_HEADERS_OK}"
  echo "BFF_SHADOW_FIREFORGET_OK=${BFF_SHADOW_FIREFORGET_OK}"
  echo "RUNTIME_SHADOW_PROOF_OK=${RUNTIME_SHADOW_PROOF_OK}"

  # BUTLER-SSOT
  echo "BUTLER_SSOT_V1_1_OK=${BUTLER_SSOT_V1_1_OK}"

  # ALGO-CORE-GATEWAY-DOC
  echo "ALGO_CORE_GATEWAY_DEPLOY_DOC_OK=${ALGO_CORE_GATEWAY_DEPLOY_DOC_OK}"

  echo "ALGO_CORE_PROD_SSOT_PRESENT_OK=${ALGO_CORE_PROD_SSOT_PRESENT_OK}"
  echo "ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=${ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK}"
  echo "ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=${ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK}"
  echo "ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=${ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK}"
  # ALGO-CORE-04
  echo "ALGO_CORE_RUNTIME_ROUTE_PRESENT_OK=${ALGO_CORE_RUNTIME_ROUTE_PRESENT_OK}"
  echo "ALGO_CORE_RUNTIME_PROD_FAILCLOSED_KEYS_OK=${ALGO_CORE_RUNTIME_PROD_FAILCLOSED_KEYS_OK}"

  # ALGO-CORE-01~03
  echo "ALGO_META_ONLY_FAILCLOSED_OK=${ALGO_META_ONLY_FAILCLOSED_OK}"
  echo "ALGO_THREE_BLOCKS_NO_RAW_OK=${ALGO_THREE_BLOCKS_NO_RAW_OK}"
  echo "ALGO_SIGNED_MANIFEST_VERIFY_OK=${ALGO_SIGNED_MANIFEST_VERIFY_OK}"
  echo "ALGO_P95_HOOK_OK=${ALGO_P95_HOOK_OK}"
  echo "ALGO_CORE_DELIVERED_KEYSET_PRESENT_OK=${ALGO_CORE_DELIVERED_KEYSET_PRESENT_OK}"
  echo "ALGO_CORE_DELIVERED_KEYSET_GUARD_OK=${ALGO_CORE_DELIVERED_KEYSET_GUARD_OK}"
}
trap cleanup EXIT

run_guard() {
  local name="$1"; shift
  local out=""
  set +e
  out="$("$@" 2>&1)"
  local rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "FAIL: ${name}"
    echo "$out"
    exit 1
  fi
  # Return output for DoD key extraction (if needed)
  echo "$out"
}

# Existing guards
echo "== guard: verify purity (no install in verify) =="
run_guard "verify purity (no install in verify)" bash scripts/verify/verify_verify_purity_no_install.sh
VERIFY_PURITY_NO_INSTALL_OK=1

echo "== guard: verify purity full scope (SSOT allowlist) =="
run_guard "verify purity full scope" bash scripts/verify/verify_verify_purity_full_scope.sh
VERIFY_PURITY_FULL_SCOPE_OK=1
VERIFY_PURITY_ALLOWLIST_SSOT_OK=1
VERIFY_PURITY_FULL_SCOPE_OK=1
VERIFY_PURITY_ALLOWLIST_SSOT_OK=1

echo "== guard: verify no /dev/tcp in verify (P3-PREP-00) =="
run_guard "verify no /dev/tcp in verify" bash scripts/verify/verify_no_dev_tcp_in_verify_v1.sh
VERIFY_NO_DEV_TCP_IN_VERIFY_OK=1

echo "== guard: verify ripgrep guard present v1 (P3-PREP-00, enforcement pending) =="
run_guard "verify ripgrep guard present v1" bash scripts/verify/verify_ripgrep_guard_present_v1.sh
VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=1

echo "== guard: verify workflow preflight present v1 (P3-PLAT-01) =="
run_guard "workflow preflight ssot v1" bash scripts/verify/verify_workflow_preflight_present_v1.sh

echo "== guard: verify runtime guard helpers adopted v1 (P3-PLAT-02) =="
run_guard "verify runtime guard helpers adopted v1" bash scripts/verify/verify_runtime_guard_helpers_adopted_v1.sh
RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=1

echo "== guard: repo contracts hygiene =="
run_guard "repo contracts hygiene" bash scripts/verify/verify_repo_contracts_hygiene.sh
REPO_CONTRACTS_HYGIENE_OK=1

echo "== guard: product-verify workflow template (SSOT) =="
run_guard "product-verify workflow template" bash scripts/verify/verify_product_verify_workflows.sh
PRODUCT_VERIFY_WORKFLOW_TEMPLATE_OK=1

echo "== guard: docs banned phrases =="
run_guard "docs banned phrases" bash scripts/verify/verify_docs_banned_phrases.sh
DOCS_NO_BANNED_PHRASES_OK=1

echo "== guard: onprem real-world proof =="
run_guard "onprem real-world proof" bash scripts/verify/verify_onprem_real_world_proof.sh
ONPREM_REAL_WORLD_PROOF_OK=1
ONPREM_REAL_WORLD_PROOF_FORMAT_OK=1

echo "== guard: onprem proof latest + archive =="
run_guard "onprem proof latest" bash scripts/verify/verify_onprem_proof_latest.sh
ONPREM_PROOF_LATEST_PRESENT_OK=1
ONPREM_PROOF_ARCHIVE_LINKED_OK=1
ONPREM_PROOF_SENSITIVE_SCAN_OK=1

echo "== guard: onprem proof freshness =="
run_guard "onprem proof freshness" bash scripts/verify/verify_onprem_proof_freshness.sh
ONPREM_PROOF_LATEST_FRESH_OK=1

echo "== guard: forbid log-grep verdict patterns =="
run_guard "forbid log-grep verdict patterns" bash scripts/verify/verify_no_log_grep_verdict.sh
NO_LOG_GREP_VERDICT_OK=1

echo "== guard: forbid install fallback in verify scripts =="
run_guard "forbid install fallback" bash scripts/verify/verify_no_npm_install_fallback.sh
NO_NPM_INSTALL_FALLBACK_OK=1

echo "== guard: JCS single source =="
run_guard "JCS single source" bash scripts/verify/verify_jcs_single_source.sh
CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1

# SLSA provenance min: product-verify-supplychain 워크플로에서만 실행
# (repo-guards에서는 파일이 생성되지 않으므로 건너뜀)
if [[ "${GITHUB_WORKFLOW:-}" == "product-verify-supplychain" ]]; then
  echo "== guard: SLSA provenance min (CI fail-closed) =="
  run_guard "SLSA provenance min" bash scripts/verify/verify_slsa_provenance_min.sh
else
  echo "== guard: SLSA provenance min (SKIP: not in product-verify-supplychain workflow) =="
fi

run_guard "repo OK contamination guard" bash scripts/verify/verify_repo_no_ok_contamination.sh
OK_CONTAMINATION_REPO_GUARD_OK=1

run_guard "repo merge_group coverage guard" bash scripts/verify/verify_repo_required_checks_have_merge_group.sh
REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1

run_guard "repo SSOT doc gate" bash scripts/verify/verify_repo_ssot_no_placeholders.sh
SSOT_PLACEHOLDER_GUARD_OK=1

run_guard "repo required check name stability" bash scripts/verify/verify_repo_required_check_name_stability.sh
REQUIRED_CHECK_NAME_STABILITY_OK=1

run_guard "repo no skipped bypass" bash scripts/verify/verify_repo_no_skipped_bypass.sh
REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=1

# New guards (H3.4-prep)
echo "== guard: lockfiles tracked =="
run_guard "lockfiles tracked" bash scripts/verify/verify_lockfiles_tracked.sh
LOCKFILES_TRACKED_OK=1

echo "== guard: required check context single (SSOT) =="
run_guard "required check context single" bash scripts/verify/verify_required_check_context_ssot_single.sh
REQUIRED_CHECK_CONTEXT_SINGLE_OK=1

echo "== guard: dual-impl drift (audit_append) =="
run_guard "audit_append no drift" bash scripts/verify/verify_audit_append_no_drift.sh
AUDIT_APPEND_NO_DRIFT_OK=1

echo "== guard: dual-impl drift (counters) =="
run_guard "counters no drift" bash scripts/verify/verify_counters_no_drift.sh
COUNTERS_NO_DRIFT_OK=1

echo "== guard: .artifacts not tracked =="
run_guard ".artifacts not tracked" bash scripts/verify/verify_no_tracked_artifacts.sh
ARTIFACTS_NOT_TRACKED_OK=1

echo "== guard: required workflows always-reported (SSOT) =="
run_guard "required workflows always-reported" bash scripts/verify/verify_required_workflows_always_reported.sh
REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=1

echo "== guard: policy header bundle fail-closed =="
run_guard "policy header bundle" bash scripts/verify/verify_policy_header_bundle_failclosed.sh
POLICY_HEADERS_REQUIRED_OK=1
POLICY_HEADERS_FAILCLOSED_OK=1

echo "== guard: meta-only allowlist enforced =="
run_guard "meta-only allowlist enforced" bash scripts/verify/verify_meta_only_allowlist_enforced.sh
META_ONLY_ALLOWLIST_ENFORCED_OK=1


echo "== guard: algo-core-06 prod key management (SSOT + keygen + fail-closed) =="
run_guard "algo-core-06 prod keys" bash scripts/verify/verify_algo_core_06_prod_keys.sh
ALGO_CORE_PROD_SSOT_PRESENT_OK=1
ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=1
ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=1
ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=1

echo "== guard: butler runtime v0 skeleton =="
run_guard "butler runtime v0 skeleton" bash scripts/verify/verify_runtime_v0_skeleton.sh
RUNTIME_V0_HTTP_OK=1
RUNTIME_EGRESS_DENY_DEFAULT_OK=1

echo "== guard: butler runtime shadow mode =="
run_guard "butler runtime shadow" bash scripts/verify/verify_runtime_shadow.sh
RUNTIME_SHADOW_ENDPOINT_OK=1
RUNTIME_SHADOW_HEADERS_OK=1
BFF_SHADOW_FIREFORGET_OK=1
RUNTIME_SHADOW_PROOF_OK=1



echo "== guard: runtime egress env proof (compose + k8s) =="
run_guard "runtime egress env proof" bash scripts/verify/verify_runtime_egress_env_proof.sh
RUNTIME_EGRESS_ENV_TEMPLATE_OK=1
RUNTIME_EGRESS_ENV_PROOF_OK=1

echo "== guard: modelpack v0 signed manifest + fail-closed =="
run_guard "modelpack v0 failclosed" bash scripts/verify/verify_modelpack_v0_failclosed.sh
MODEL_PACK_SCHEMA_SSOT_OK=1
MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=1
MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=1
MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=1
MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=1

echo "== guard: model pack apply fail-closed e2e =="
run_guard "model pack apply fail-closed e2e" bash scripts/verify/verify_model_pack_apply_failclosed_e2e.sh
ALGO_APPLY_FAILCLOSED_E2E_OK=1
ALGO_APPLY_STATE_UNCHANGED_OK=1
ALGO_APPLY_REASON_CODE_PRESERVED_OK=1

echo "== guard: model pack v0 identity + expiry =="
run_guard "model pack v0 identity + expiry" bash scripts/verify/verify_modelpack_v0_identity_expiry.sh
MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=1
MODEL_PACK_V0_EXPIRES_ENFORCED_OK=1

echo "== guard: model pack v0 compat =="
run_guard "model pack v0 compat" bash scripts/verify/verify_modelpack_v0_compat.sh
MODEL_PACK_V0_COMPAT_FIELDS_REQUIRED_OK=1
MODEL_PACK_V0_COMPAT_ENFORCED_OK=1

echo "== guard: ondevice model exec v0 (Track B-1) =="
run_guard "ondevice model exec v0" bash scripts/verify/verify_ondevice_model_exec_v0.sh
ONDEVICE_MODEL_EXEC_V0_OK=1
MODEL_PACK_VERIFY_REQUIRED_OK=1
ONDEVICE_EGRESS_DENY_PROOF_OK=1
ONDEVICE_NO_RAW_STORAGE_OK=1

echo "== guard: ondevice real compute once (Track B-1.1) =="
run_guard "ondevice real compute once" bash scripts/verify/verify_ondevice_real_compute_once.sh
ONDEVICE_REAL_COMPUTE_ONCE_OK=1
ONDEVICE_RESULT_FINGERPRINT_OK=1
ONDEVICE_COMPUTE_PATH_ONDEVICE_OK=1

echo "== guard: ondevice inference v0 (P2-AI-01) =="
run_guard "ondevice inference v0" bash scripts/verify/verify_ondevice_inference_v0.sh
ONDEVICE_MODEL_PACK_LOADED_OK=1
ONDEVICE_MODEL_PACK_IDENTITY_OK=1
ONDEVICE_INFERENCE_ONCE_OK=1
ONDEVICE_OUTPUT_FINGERPRINT_OK=1
ONDEVICE_INFER_USES_PACK_PARAMS_OK=1

echo "== guard: ai v1 modules (perf/rerank/calib/propensity) =="
run_guard "ai v1 modules" bash scripts/verify/verify_ai_v1_modules.sh
AI_PERF_HARNESS_V1_OK=1
AI_RERANK_NEARTIE_V1_OK=1
AI_CALIB_V1_OK=1
AI_PROPENSITY_IPS_SNIPS_V1_OK=1
AI_DETERMINISM_OK=1
AI_P95_BUDGET_OK=1
AI_NEARTIE_SWAP_BUDGET_OK=1

echo "== guard: ai budget gates (P2-AI-02: latency/mem/energy_proxy) =="
GUARD_OUT="$(run_guard "ai budget gates" bash scripts/verify/verify_ai_budget_gates_v0.sh)"
# Extract DoD keys from guard output (use eval to set in parent shell)
eval "$(echo "$GUARD_OUT" | grep -E '^(AI_RESOURCE_BUDGET_|AI_BUDGET_MEASUREMENTS_|AI_ENERGY_PROXY_)')" || true

echo "== guard: algo determinism gate (D0) =="
run_guard "algo determinism gate (D0)" bash scripts/verify/verify_algo_determinism_gate.sh
ALGO_DETERMINISM_VERIFIED_OK=1
ALGO_DETERMINISM_HASH_MATCH_OK=1
ALGO_DETERMINISM_MODE_REPORTED_OK=1

echo "== guard: ops hub v0 meta-only =="
run_guard "ops hub v0 meta-only" bash scripts/verify/verify_ops_hub_v0_meta_only.sh
OPS_HUB_META_SCHEMA_SSOT_OK=1
OPS_HUB_NO_RAW_TEXT_GUARD_OK=1
OPS_HUB_REPORT_V0_OK=1
OPS_HUB_REPORT_INPUT_META_ONLY_OK=1

echo "== guard: ops hub traceability (request_id join) =="
run_guard "ops hub traceability" bash scripts/verify/verify_ops_hub_traceability.sh
OPS_HUB_TRACEABILITY_OK=1
OPS_HUB_TRACEABILITY_REPORT_OK=1
OPS_HUB_TRACEABILITY_NO_RAW_OK=1

echo "== guard: ops hub trace realpath (persistence + idempotency) =="
run_guard "ops hub trace realpath" bash scripts/verify/verify_ops_hub_trace_realpath.sh
OPS_HUB_TRACE_REALPATH_PERSISTED_OK=1
OPS_HUB_TRACE_REALPATH_JOINABLE_OK=1
OPS_HUB_TRACE_REALPATH_NO_RAW_OK=1
OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=1

echo "== guard: ops hub trace service store =="
run_guard "ops hub trace service store" bash scripts/verify/verify_ops_hub_trace_service_store.sh
OPS_HUB_TRACE_SERVICE_PERSIST_OK=1
OPS_HUB_TRACE_IDEMPOTENT_OK=1
OPS_HUB_TRACE_NO_RAW_OK=1
OPS_HUB_TRACE_JOINABLE_OK=1

echo "== guard: trace security lockdown (A-3.1) =="
run_guard "trace security lockdown (A-3.1)" bash scripts/verify/verify_trace_security_lockdown.sh
OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1

echo "== guard: ops hub trace db store (P1-PLAT-01) =="
run_guard "ops hub trace db store" bash scripts/verify/verify_ops_hub_trace_db_store.sh
OPS_HUB_TRACE_DB_SCHEMA_OK=1
OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=1
OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=1
OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=1
OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=1

echo "== guard: reason codes v1 single source =="
run_guard "reason codes v1 single source" bash scripts/verify/verify_reason_codes_v1_single_source.sh
REASON_CODE_SINGLE_SOURCE_OK=1
REASON_CODE_DRIFT_GUARD_OK=1

echo "== guard: m6 sealed record =="
run_guard "m6 sealed record" bash scripts/verify/verify_m6_sealed_record.sh
M6_SEALED_RECORD_PRESENT_OK=1
M6_SEALED_RECORD_NO_PLACEHOLDER_OK=1
M6_SEALED_RECORD_PR_MAP_OK=1

echo "== guard: m7 sealed record =="
run_guard "m7 sealed record" bash scripts/verify/verify_m7_sealed_record.sh
M7_SEALED_RECORD_PRESENT_OK=1
M7_SEALED_RECORD_FORMAT_OK=1
M7_SEALED_RECORD_NO_PLACEHOLDER_OK=1

echo "== guard: butler ssot v1.1 =="
run_guard "butler ssot v1.1" bash scripts/verify/verify_butler_ssot_v1_1.sh
BUTLER_SSOT_V1_1_OK=1

echo "== guard: algo-core gateway deployment doc =="
run_guard "algo-core gateway deploy doc" bash scripts/verify/verify_algo_core_gateway_deploy_doc.sh
ALGO_CORE_GATEWAY_DEPLOY_DOC_OK=1

echo "== guard: meta-only validator parity (client/server single source) =="
run_guard "meta-only validator parity" bash scripts/verify/verify_meta_only_validator_parity.sh
META_ONLY_VALIDATOR_PARITY_OK=1

run_guard "meta-only validator single source (Track A-2)" bash scripts/verify/verify_meta_only_validator_single_source.sh
META_ONLY_VALIDATOR_SINGLE_SOURCE_OK=1
META_ONLY_VALIDATOR_NO_DUPLICATION_OK=1
META_ONLY_VALIDATOR_V1_CJS_PRESENT_OK=1

echo "== guard: algo-core-04 runtime wiring assets =="
run_guard "algo-core-04 runtime wiring assets" bash scripts/verify/verify_algo_core_04_runtime_wiring.sh
ALGO_CORE_RUNTIME_ROUTE_PRESENT_OK=1
ALGO_CORE_RUNTIME_PROD_FAILCLOSED_KEYS_OK=1

echo "== guard: export two-step + auditv2 =="
run_guard "export two-step + auditv2" bash scripts/verify/verify_export_two_step_auditv2.sh
EXPORT_TWO_STEP_OK=1
EXPORT_APPROVAL_AUDITED_OK=1
EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=1
EXPORT_APPROVE_AUDIT_V2_OK=1

echo "== guard: mock network zero =="
run_guard "mock network zero" bash scripts/verify/verify_mock_network_zero.sh
MOCK_NETWORK_ZERO_OK=1

echo "== guard: perf p95 budget gate =="
run_guard "perf p95 budget gate" bash scripts/verify/verify_perf_p95_budget.sh
PERF_P95_BUDGET_DEFINED_OK=1
PERF_P95_CONTRACT_OK=1
PERF_P95_REGRESSION_BLOCK_OK=1

echo "== guard: perf p95 baseline pinned (SSOT) =="
run_guard "perf p95 baseline pinned" bash scripts/verify/verify_perf_p95_baseline_pinned.sh
PERF_P95_BASELINE_PINNED_OK=1

echo "== guard: onprem compose quickstart assets =="
run_guard "onprem compose quickstart assets" bash scripts/verify/verify_onprem_compose_quickstart_assets.sh
ONPREM_COMPOSE_ASSETS_OK=1

echo "== guard: onprem helm skeleton assets =="
run_guard "onprem helm skeleton assets" bash scripts/verify/verify_onprem_helm_skeleton_assets.sh
ONPREM_HELM_SKELETON_OK=1

echo "== guard: helm secrets enabled guard =="
run_guard "helm secrets enabled guard" bash scripts/verify/verify_onprem_helm_secrets_guard.sh
ONPREM_HELM_SECRETS_GUARD_OK=1

echo "== guard: onprem helm template smoke ==" 
run_guard "onprem helm template smoke" bash scripts/verify/verify_onprem_helm_template_smoke.sh
ONPREM_HELM_TEMPLATE_SMOKE_OK=1
ONPREM_HELM_TEMPLATE_SECRET_REF_OK=1

echo "== guard: onprem signing key policy (prod fail-closed) =="
run_guard "onprem signing key policy" bash scripts/verify/verify_onprem_signing_key_policy.sh
ONPREM_SIGNING_KEY_REQUIRED_OK=1
ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=1
ONPREM_KEY_ID_ALLOWLIST_OK=1

echo "== guard: onprem signed bundle verify (manifest+sig) =="
run_guard "onprem signed bundle verify" bash scripts/verify/verify_onprem_signed_bundle.sh
ONPREM_SIGNED_BUNDLE_OK=1

echo "== guard: onprem install/verify assets == "
run_guard "onprem install/verify assets" bash scripts/verify/verify_onprem_install_verify_assets.sh
ONPREM_INSTALL_VERIFY_OK=1

echo "== guard: onprem delivered keyset (SSOT) =="
SSOT_FILE="docs/ops/contracts/ONPREM_DELIVERED_KEYS_SSOT.md"
test -s "$SSOT_FILE" || { echo "BLOCK: missing SSOT file: $SSOT_FILE"; exit 1; }
ONPREM_DELIVERED_KEYSET_PRESENT_OK=1

# Parse required keys from SSOT and ensure each variable is exactly 1
REQ_KEYS="$(sed -n 's/^- //p' "$SSOT_FILE" | tr -d '\r' | sed '/^$/d')"
test -n "$REQ_KEYS" || { echo "BLOCK: SSOT has no required keys"; exit 1; }
while IFS= read -r k; do
  v="${!k:-}"
  if [[ "$v" != "1" ]]; then
    echo "BLOCK: delivered key not satisfied: ${k}=${v:-<unset>}"
    exit 1
  fi
done <<< "$REQ_KEYS"
ONPREM_DELIVERED_KEYSET_GUARD_OK=1

echo "== guard: test event selection (reason_code requires action) =="
run_guard "test event selection" bash scripts/verify/verify_test_event_selection_guard.sh
TEST_EVENT_SELECTION_GUARD_OK=1

echo "== guard: prod delivered keyset (SSOT) =="
SSOT_FILE="docs/ops/contracts/PROD_DELIVERED_KEYS_SSOT.md"
test -s "$SSOT_FILE" || { echo "BLOCK: missing SSOT file: $SSOT_FILE"; exit 1; }
PROD_DELIVERED_KEYSET_PRESENT_OK=1

REQ_KEYS="$(sed -n 's/^- //p' "$SSOT_FILE" | tr -d '\r' | sed '/^$/d')"
test -n "$REQ_KEYS" || { echo "BLOCK: SSOT has no required keys"; exit 1; }

# Each required key must be exactly 1 in this script's variables (no recursion)
while IFS= read -r k; do
  v="${!k:-}"
  if [[ "$v" != "1" ]]; then
    echo "BLOCK: delivered key not satisfied: ${k}=${v:-<unset>}"
    exit 1
  fi
done <<< "$REQ_KEYS"

PROD_DELIVERED_KEYSET_GUARD_OK=1

echo "== guard: algo-core 01~03 (meta-only + 3 blocks + signed manifest + p95) =="
run_guard "algo-core 01~03" bash scripts/verify/verify_algo_core_01_03.sh
ALGO_META_ONLY_FAILCLOSED_OK=1
ALGO_THREE_BLOCKS_NO_RAW_OK=1
ALGO_SIGNED_MANIFEST_VERIFY_OK=1
ALGO_P95_HOOK_OK=1

echo "== guard: algo-core delivered keyset (SSOT) =="
SSOT_FILE="docs/ops/contracts/ALGO_CORE_DELIVERED_KEYS_SSOT.md"
test -s "$SSOT_FILE" || { echo "BLOCK: missing SSOT file: $SSOT_FILE"; exit 1; }
ALGO_CORE_DELIVERED_KEYSET_PRESENT_OK=1

REQ_KEYS="$(sed -n 's/^- //p' "$SSOT_FILE" | tr -d '\r' | sed '/^$/d')"
test -n "$REQ_KEYS" || { echo "BLOCK: SSOT has no required keys"; exit 1; }

while IFS= read -r k; do
  v="${!k:-}"
  if [[ "$v" != "1" ]]; then
    echo "BLOCK: delivered key not satisfied: ${k}=${v:-<unset>}"
    exit 1
  fi
done <<< "$REQ_KEYS"

ALGO_CORE_DELIVERED_KEYSET_GUARD_OK=1

echo "== guard: web ux-01 assets (E2E fixture) =="
run_guard "web ux-01 assets" bash scripts/verify/verify_web_ux_01_assets.sh
WEB_E2E_MODE_SWITCH_WIRED_OK=1
WEB_E2E_MOCK_NETWORK_ZERO_OK=1
WEB_E2E_LIVE_HEADER_BUNDLE_OK=1

echo "== guard: web ux-03 assets (export approve auditv2 e2e) =="
run_guard "web ux-03 assets" bash scripts/verify/verify_web_ux_03_assets.sh
WEB_E2E_EXPORT_TWO_STEP_OK=1
WEB_E2E_EXPORT_AUDITV2_OK=1
EXPORT_APPROVE_IDEMPOTENT_OK=1
EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=1

echo "== guard: web ux-04 assets (p95 marks parity e2e) =="
run_guard "web ux-04 assets" bash scripts/verify/verify_web_ux_04_assets.sh
PERF_E2E_EVENT_MARKS_WIRED_OK=1
PERF_E2E_MARKS_PARITY_OK=1

echo "== guard: perf real pipeline p95 (wired + ops hub join + budget) =="
run_guard "perf real pipeline p95" bash scripts/verify/verify_perf_real_pipeline_p95.sh
PERF_REAL_PIPELINE_WIRED_OK=1
PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=1
PERF_REAL_PIPELINE_NO_RAW_OK=1
PERF_REAL_PIPELINE_P95_BUDGET_OK=1
PERF_REAL_PIPELINE_MIN_SAMPLES_OK=1
PERF_REAL_PIPELINE_VARIANCE_OK=1

echo "== guard: web ux-08 assets (meta-only negative suite) =="
run_guard "web ux-08 assets" bash scripts/verify/verify_web_ux_08_assets.sh
WEB_META_ONLY_NEGATIVE_SUITE_OK=1

echo "== guard: workflow-lint sealed (no attestation) =="
if grep -qE 'id-token:[[:space:]]*write|attestations:[[:space:]]*write|artifact-metadata:[[:space:]]*write|attest-build-provenance' \
  .github/workflows/workflow-lint.yml; then
  echo "BLOCK: workflow-lint has forbidden attestation permissions/steps"
  exit 1
fi
echo "WORKFLOW_LINT_SEALED_OK=1"

exit 0
