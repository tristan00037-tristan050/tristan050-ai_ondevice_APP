#!/usr/bin/env bash
set -euo pipefail

OK_CONTAMINATION_REPO_GUARD_OK=0
REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=0
SSOT_PLACEHOLDER_GUARD_OK=0
REQUIRED_CHECK_NAME_STABILITY_OK=0
REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=0
NO_LOG_GREP_VERDICT_OK=0
NO_NPM_INSTALL_FALLBACK_OK=0
CANONICALIZE_SHARED_SINGLE_SOURCE_OK=0
TEST_EVENT_SELECTION_GUARD_OK=0

# PROD Delivered Keyset
PROD_DELIVERED_KEYSET_PRESENT_OK=0
PROD_DELIVERED_KEYSET_GUARD_OK=0

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
}

# Existing guards
echo "== guard: forbid log-grep verdict patterns =="
run_guard "forbid log-grep verdict patterns" bash scripts/verify/verify_no_log_grep_verdict.sh
NO_LOG_GREP_VERDICT_OK=1

echo "== guard: forbid npm install fallback in verify scripts =="
run_guard "forbid npm install fallback" bash scripts/verify/verify_no_npm_install_fallback.sh
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

echo "== guard: butler ssot v1.1 =="
run_guard "butler ssot v1.1" bash scripts/verify/verify_butler_ssot_v1_1.sh
BUTLER_SSOT_V1_1_OK=1

echo "== guard: algo-core gateway deployment doc =="
run_guard "algo-core gateway deploy doc" bash scripts/verify/verify_algo_core_gateway_deploy_doc.sh
ALGO_CORE_GATEWAY_DEPLOY_DOC_OK=1

echo "== guard: meta-only validator parity (client/server single source) =="
run_guard "meta-only validator parity" bash scripts/verify/verify_meta_only_validator_parity.sh
META_ONLY_VALIDATOR_PARITY_OK=1

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

exit 0
