#!/usr/bin/env bash
# S7 Step4-B B PR 메타데이터 자동 생성 (정본)
# Preflight PASS가 전제이며, PASS가 아니면 즉시 중단됩니다.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

# 0) PR 생성 전 필수 게이트(10초)
bash docs/ops/R10S7_STEP4B_B_PR_PREFLIGHT_CHECK.sh

# 1) 현재 브랜치명 자동 감지
BR="$(git branch --show-current)"
if [ -z "$BR" ]; then
  echo "FAIL: could not detect current branch"
  exit 1
fi
if [ "$BR" = "main" ]; then
  echo "FAIL: current branch is main. switch to your improvement branch and re-run."
  exit 1
fi

# 2) PR 생성 메타데이터 출력(복붙용)
echo ""
echo "=== Step4-B B PR (Ready-to-Paste) ==="
echo "Base   : main"
echo "Compare: $BR"
echo "Title  : feat(s7): step4-b-b strict improvement under regression gate (input fixed)"
echo ""
echo "----- PR Body (SSOT: PR_BODY.md) -----"
cat docs/ops/R10S7_STEP4B_B_PR_BODY.md
echo ""
echo "----- (END) -----"

