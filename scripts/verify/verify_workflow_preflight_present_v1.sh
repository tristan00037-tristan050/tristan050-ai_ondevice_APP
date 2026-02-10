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

# 스코프는 "내용"이 아니라 "파일명"으로 고정한다.
# - product-verify-*.yml / product-verify-*.yaml 은 반드시 PREP_TOKEN=1 포함해야 함
# - 스코프 파일이 0개면 fail-closed

MISSING=0
FOUND_ANY=0

for f in .github/workflows/product-verify-*.yml .github/workflows/product-verify-*.yaml; do
  [ -f "$f" ] || continue
  FOUND_ANY=1
  if ! grep -q "PREP_TOKEN=1" "$f"; then
    echo "BLOCK: PREP_TOKEN=1 missing in $f"
    MISSING=1
  fi
done

if [ "$FOUND_ANY" -ne 1 ]; then
  echo "BLOCK: no product-verify-* workflow files found"
  exit 1
fi

if [ "$MISSING" -ne 0 ]; then
  exit 1
fi

WORKFLOW_PREFLIGHT_PRESENT_OK=1
exit 0
