#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

GLOB_DIR=".github/workflows"
test -d "$GLOB_DIR" || { echo "BLOCK: missing $GLOB_DIR"; exit 1; }

FILES="$(ls -1 ${GLOB_DIR}/product-verify-*.yml 2>/dev/null || true)"
test -n "$FILES" || { echo "BLOCK: no product-verify-*.yml found"; exit 1; }

EXCEPT_SSOT="docs/ops/contracts/PRODUCT_VERIFY_WORKFLOW_TEMPLATE_EXCEPTIONS_V1.md"

is_exception() {
  local f="$1"
  test -f "$EXCEPT_SSOT" || return 1
  rg -qF "$f" "$EXCEPT_SSOT"
}

FAIL=0

for f in $FILES; do
  # 1) triggers: pull_request / merge_group / workflow_dispatch
  # Exception: 예외 목록에 있는 파일은 pull_request/merge_group 불필요, 대신 schedule/workflow_dispatch 필수
  if is_exception "$f"; then
    # 예외는 schedule/workflow_dispatch만 요구
    rg -q "workflow_dispatch" "$f" || { echo "FAIL: missing workflow_dispatch in $f"; exit 1; }
    rg -q "schedule" "$f" || { echo "FAIL: missing schedule in $f"; exit 1; }
  else
    # 일반은 pull_request + merge_group 요구
    rg -q "pull_request" "$f" || { echo "FAIL: missing pull_request in $f"; exit 1; }
    rg -q "merge_group" "$f" || { echo "FAIL: missing merge_group in $f"; exit 1; }
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
