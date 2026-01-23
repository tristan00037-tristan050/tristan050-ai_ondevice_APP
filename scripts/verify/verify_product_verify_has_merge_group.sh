#!/usr/bin/env bash
set -euo pipefail

# Guard: product-verify-* workflows must be always reported in PR + merge queue.
# - Must include triggers: pull_request, merge_group, workflow_dispatch
# - Must NOT use workflow-level paths/paths-ignore filters (skip risk)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WF_DIR=".github/workflows"
[[ -d "$WF_DIR" ]] || { echo "FAIL: missing $WF_DIR"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1; }
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

shopt -s nullglob
FILES=("$WF_DIR"/product-verify-*.yml "$WF_DIR"/product-verify-*.yaml)
shopt -u nullglob

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "FAIL: no product-verify-* workflow files found under $WF_DIR"
  exit 1
fi

fail=0
for f in "${FILES[@]}"; do
  for kw in pull_request merge_group workflow_dispatch; do
    if ! has_token "$kw" "$f"; then
      echo "FAIL: $f missing trigger token: $kw"
      fail=1
    fi
  done

  if has_paths_filter "$f"; then
    echo "FAIL: $f contains paths/paths-ignore (skip risk)"
    fail=1
  fi
done

[[ $fail -eq 0 ]] || exit 1
echo "REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1"

