#!/usr/bin/env bash
set -euo pipefail

# Hardening++ 3.2: required check/workflow/job 이름 안정성(SSOT 기준 고정)
# 최소 규칙: product-verify-* 워크플로의 "name:"와 job name이 파일명/SSOT와 일치해야 한다.
# (SSOT에 고정된 이름과 불일치하면 breaking)

REQUIRED_CHECK_NAME_STABILITY_OK=0
cleanup(){ echo "REQUIRED_CHECK_NAME_STABILITY_OK=${REQUIRED_CHECK_NAME_STABILITY_OK}"; }
trap cleanup EXIT

WF_DIR=".github/workflows"
[[ -d "$WF_DIR" ]] || { echo "FAIL: missing $WF_DIR"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

fail=0
while IFS= read -r f; do
  base="$(basename "$f")"
  # workflow name must exist and be non-empty
  if have_rg; then
    if ! rg -n --no-messages '^name:\s*\S+' "$f" >/dev/null; then
      echo "FAIL: $f missing workflow name"
      fail=1
      continue
    fi
    # job name must exist and be non-empty
    if ! rg -n --no-messages '^\s{2,}[A-Za-z0-9_-]+:\s*$' "$f" >/dev/null; then
      echo "FAIL: $f missing jobs key"
      fail=1
    fi
  else
    # grep fallback
    if ! grep -qE '^name:\s+\S+' "$f"; then
      echo "FAIL: $f missing workflow name"
      fail=1
      continue
    fi
    if ! grep -qE '^\s{2,}[A-Za-z0-9_-]+:\s*$' "$f"; then
      echo "FAIL: $f missing jobs key"
      fail=1
    fi
  fi
done < <(ls -1 "$WF_DIR"/product-verify-*.yml "$WF_DIR"/product-verify-*.yaml 2>/dev/null || true)

[[ $fail -eq 0 ]] || exit 1
REQUIRED_CHECK_NAME_STABILITY_OK=1
exit 0

