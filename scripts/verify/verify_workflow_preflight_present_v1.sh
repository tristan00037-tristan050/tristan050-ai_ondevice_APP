#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_PREFLIGHT_PRESENT_OK=0
cleanup(){ echo "WORKFLOW_PREFLIGHT_PRESENT_OK=${WORKFLOW_PREFLIGHT_PRESENT_OK}"; }
trap cleanup EXIT

# SSOT 문서/토큰 확인 (fail-closed)
test -f docs/ops/contracts/WORKFLOW_PREFLIGHT_SSOT_V1.md
grep -q "WORKFLOW_PREFLIGHT_SSOT_V1_TOKEN=1" docs/ops/contracts/WORKFLOW_PREFLIGHT_SSOT_V1.md \
  || { echo "BLOCK: SSOT token missing"; exit 1; }

# product-verify 워크플로 파일 존재 확인 (fail-closed)
FOUND_ANY=0
MISSING=0

for f in .github/workflows/product-verify-*.yml .github/workflows/product-verify-*.yaml; do
  [ -f "$f" ] || continue
  FOUND_ANY=1
  if ! grep -q "PREP_TOKEN=1" "$f"; then
    echo "BLOCK: PREP_TOKEN=1 missing in $f"
    MISSING=1
  fi
done

if [ "$FOUND_ANY" -ne 1 ]; then
  echo "BLOCK: no product-verify-* workflows found"
  exit 1
fi

if [ "$MISSING" -ne 0 ]; then
  exit 1
fi

WORKFLOW_PREFLIGHT_PRESENT_OK=1
exit 0
