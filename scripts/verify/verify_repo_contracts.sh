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

# New (H3.4-prep)
LOCKFILES_TRACKED_OK=0
REQUIRED_CHECK_CONTEXT_SINGLE_OK=0
AUDIT_APPEND_NO_DRIFT_OK=0
COUNTERS_NO_DRIFT_OK=0
ARTIFACTS_NOT_TRACKED_OK=0
REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=0

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

exit 0
