#!/usr/bin/env bash
set -euo pipefail

OK_CONTAMINATION_REPO_GUARD_OK=0
REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=0
SSOT_PLACEHOLDER_GUARD_OK=0

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

echo "OK_CONTAMINATION_REPO_GUARD_OK=${OK_CONTAMINATION_REPO_GUARD_OK}"
echo "REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=${REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK}"
echo "SSOT_PLACEHOLDER_GUARD_OK=${SSOT_PLACEHOLDER_GUARD_OK}"
exit 0

