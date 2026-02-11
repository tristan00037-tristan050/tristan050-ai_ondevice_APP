#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_PREFLIGHT_PRESENT_OK=0
trap 'echo "WORKFLOW_PREFLIGHT_PRESENT_OK=$WORKFLOW_PREFLIGHT_PRESENT_OK"' EXIT

# SSOT 문서 토큰 확인
test -f docs/ops/contracts/WORKFLOW_PREFLIGHT_SSOT_V1.md
grep -q "WORKFLOW_PREFLIGHT_SSOT_V1_TOKEN=1" docs/ops/contracts/WORKFLOW_PREFLIGHT_SSOT_V1.md \
  || { echo "BLOCK: SSOT token missing"; exit 1; }

# product-verify 워크플로들에 PREP_TOKEN=1이 최소 1회 이상 존재해야 함
ls .github/workflows/product-verify-*.yml >/dev/null 2>&1 \
  || { echo "BLOCK: no product-verify workflows found"; exit 1; }

grep -RIn "PREP_TOKEN=1" .github/workflows/product-verify-*.yml >/dev/null \
  || { echo "BLOCK: missing PREP_TOKEN in product-verify workflows"; exit 1; }

WORKFLOW_PREFLIGHT_PRESENT_OK=1
exit 0
