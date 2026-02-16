#!/usr/bin/env bash
set -euo pipefail

# Hardening++: product-verify-* workflows must be always reported
# - triggers: pull_request + merge_group + workflow_dispatch
# - paths/paths-ignore 금지 (Pending/Expected 유발)
# - job-level if 금지 (전체 job skip 유발)
# PASS에서만 REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1 출력

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WF_DIR=".github/workflows"
[[ -d "$WF_DIR" ]] || { echo "FAIL: missing $WF_DIR"; exit 1; }

EXCEPT_SSOT="docs/ops/contracts/PRODUCT_VERIFY_WORKFLOW_TEMPLATE_EXCEPTIONS_V1.md"

is_exception() {
  local f="$1"
  [[ -f "$EXCEPT_SSOT" ]] || return 1
  rg -qF "$f" "$EXCEPT_SSOT" 2>/dev/null || return 1
}

have_rg() { command -v rg >/dev/null 2>&1; }

shopt -s nullglob
FILES=("$WF_DIR"/product-verify-*.yml "$WF_DIR"/product-verify-*.yaml)
shopt -u nullglob

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "FAIL: no product-verify-* workflow files found under $WF_DIR"
  exit 1
fi

fail=0

has_token() {
  local token="$1" file="$2"
  if have_rg; then
    rg -n --no-messages "\b${token}\b" "$file" >/dev/null 2>&1
  else
    grep -nE "\b${token}\b" "$file" >/dev/null 2>&1
  fi
}

has_paths_filter() {
  local file="$1"
  if have_rg; then
    rg -n --no-messages '^\s*(paths|paths-ignore)\s*:' "$file" >/dev/null 2>&1
  else
    grep -nE '^\s*(paths|paths-ignore)\s*:' "$file" >/dev/null 2>&1
  fi
}

has_job_level_if() {
  local file="$1"
  # job-level if는 보통 "    if:" (4 spaces) 형태로 등장
  if have_rg; then
    rg -n --no-messages '^\s{4}if\s*:' "$file" >/dev/null 2>&1
  else
    grep -nE '^\s{4}if\s*:' "$file" >/dev/null 2>&1
  fi
}

for f in "${FILES[@]}"; do
  # Exception: 예외 목록에 있는 파일은 pull_request/merge_group 불필요, 대신 schedule/workflow_dispatch 필수
  if is_exception "$f"; then
    # 예외는 schedule/workflow_dispatch 필수
    if ! has_token "workflow_dispatch" "$f"; then
      echo "FAIL: $f missing trigger token: workflow_dispatch (exception requires workflow_dispatch)"
      fail=1
    fi
    if ! has_token "schedule" "$f"; then
      echo "FAIL: $f missing trigger token: schedule (exception requires schedule)"
      fail=1
    fi
  else
    # 기존 규칙 유지: pull_request + merge_group 필수
    for kw in pull_request merge_group; do
      if ! has_token "$kw" "$f"; then
        echo "FAIL: $f missing trigger token: $kw"
        fail=1
      fi
    done
    # workflow_dispatch는 모든 product-verify 워크플로에 필수
    if ! has_token "workflow_dispatch" "$f"; then
      echo "FAIL: $f missing trigger token: workflow_dispatch"
      fail=1
    fi
  fi

  if has_paths_filter "$f"; then
    echo "FAIL: $f contains paths/paths-ignore (skip risk)"
    fail=1
  fi

  if has_job_level_if "$f"; then
    echo "FAIL: $f contains job-level if (skip risk)"
    fail=1
  fi
done

[[ $fail -eq 0 ]] || exit 1
echo "REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1"

