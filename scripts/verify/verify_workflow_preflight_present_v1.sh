#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_PREFLIGHT_PRESENT_OK=0
cleanup(){ echo "WORKFLOW_PREFLIGHT_PRESENT_OK=${WORKFLOW_PREFLIGHT_PRESENT_OK}"; }
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# SSOT 문서 토큰 존재 (fail-closed)
if ! grep -q "WORKFLOW_PREFLIGHT_SSOT_V1_TOKEN=1" docs/ops/contracts/WORKFLOW_PREFLIGHT_SSOT_V1.md 2>/dev/null; then
  echo "BLOCK: SSOT token missing in WORKFLOW_PREFLIGHT_SSOT_V1.md"
  exit 1
fi

# product-verify* 워크플로에서 PREP_TOKEN=1 존재 여부 검사 (POSIX)
# - 파일명/경로 오탐 줄이기 위해 .github/workflows 아래만 스캔
# - PREP_TOKEN=1 없으면 fail-closed
MISSING=0
FOUND_ANY=0

# product-verify 키워드가 있는 워크플로만 대상으로 삼음
for f in .github/workflows/*.yml .github/workflows/*.yaml; do
  [ -f "$f" ] || continue
  if grep -q "product-verify" "$f"; then
    FOUND_ANY=1
    if ! grep -q "PREP_TOKEN=1" "$f"; then
      echo "BLOCK: PREP_TOKEN=1 missing in $f"
      MISSING=1
    fi
  fi
done

if [ "$FOUND_ANY" -ne 1 ]; then
  echo "BLOCK: no product-verify workflow found"
  exit 1
fi

if [ "$MISSING" -ne 0 ]; then
  exit 1
fi

WORKFLOW_PREFLIGHT_PRESENT_OK=1
exit 0

