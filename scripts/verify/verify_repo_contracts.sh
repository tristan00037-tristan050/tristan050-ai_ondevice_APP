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

# Guard: forbid log/sentence grep verdict patterns (P1-2)
echo "== guard: forbid log-grep verdict patterns =="
bash scripts/verify/verify_no_log_grep_verdict.sh
NO_LOG_GREP_VERDICT_OK=1

echo "== guard: forbid npm install fallback in verify scripts =="
bash scripts/verify/verify_no_npm_install_fallback.sh
NO_NPM_INSTALL_FALLBACK_OK=1

echo "== guard: JCS single source =="
bash scripts/verify/verify_jcs_single_source.sh
CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1

echo "== guard: SLSA provenance min =="
bash scripts/verify/verify_slsa_provenance_min.sh || true

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

echo "OK_CONTAMINATION_REPO_GUARD_OK=${OK_CONTAMINATION_REPO_GUARD_OK}"
echo "REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=${REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK}"
echo "SSOT_PLACEHOLDER_GUARD_OK=${SSOT_PLACEHOLDER_GUARD_OK}"
echo "REQUIRED_CHECK_NAME_STABILITY_OK=${REQUIRED_CHECK_NAME_STABILITY_OK}"
echo "REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK=${REQUIRED_CHECK_NO_SKIPPED_BYPASS_OK}"
echo "NO_LOG_GREP_VERDICT_OK=${NO_LOG_GREP_VERDICT_OK}"
echo "NO_NPM_INSTALL_FALLBACK_OK=${NO_NPM_INSTALL_FALLBACK_OK}"
echo "CANONICALIZE_SHARED_SINGLE_SOURCE_OK=${CANONICALIZE_SHARED_SINGLE_SOURCE_OK}"
exit 0

