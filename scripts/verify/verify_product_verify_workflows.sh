#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

GLOB_DIR=".github/workflows"
test -d "$GLOB_DIR" || { echo "BLOCK: missing $GLOB_DIR"; exit 1; }

FILES="$(ls -1 ${GLOB_DIR}/product-verify-*.yml 2>/dev/null || true)"
test -n "$FILES" || { echo "BLOCK: no product-verify-*.yml found"; exit 1; }

FAIL=0

for f in $FILES; do
  # 1) triggers: pull_request / merge_group / workflow_dispatch
  # 패턴: pull_request: 또는 pull_request: {} 모두 허용
  if ! rg -n '^\s*pull_request\s*:' "$f" >/dev/null; then
    echo "FAIL: missing pull_request in $f"
    FAIL=1
  fi
  if ! rg -n '^\s*merge_group\s*:' "$f" >/dev/null; then
    echo "FAIL: missing merge_group in $f"
    FAIL=1
  fi
  if ! rg -n '^\s*workflow_dispatch\s*:' "$f" >/dev/null; then
    echo "FAIL: missing workflow_dispatch in $f"
    FAIL=1
  fi

  # 2) job-level if 금지 (jobs 블록 하위에서 if: 감지)
  # jobs.<job>.if 패턴만 차단 (2칸 들여쓰기 + if:)
  # step-level if (4칸 이상 들여쓰기)는 허용
  JOB_IF_LINES="$(rg -n '^\s{2,3}if\s*:\s*' "$f" || true)"
  if [[ -n "$JOB_IF_LINES" ]]; then
    echo "FAIL: job-level if detected (skip risk) in $f"
    echo "$JOB_IF_LINES"
    FAIL=1
  fi

  # 3) gate job 존재(최소)
  rg -n '^\s*gate\s*:\s*$' "$f" >/dev/null || { echo "FAIL: missing gate job in $f"; FAIL=1; }
done

# 4) SSOT 문서 존재 확인
test -s "docs/ops/contracts/WORKFLOW_PRODUCT_VERIFY_SSOT.md" || { echo "BLOCK: missing SSOT doc"; exit 1; }

if [[ "$FAIL" != "0" ]]; then
  exit 1
fi

echo "PRODUCT_VERIFY_WORKFLOW_TEMPLATE_OK=1"
exit 0
