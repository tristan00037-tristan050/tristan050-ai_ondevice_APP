#!/usr/bin/env bash
set -euo pipefail

# 목적: 테스트/검증 스크립트에서 OK=1을 "하드코딩"으로 통과시키는 패턴을 차단한다.
# 원칙: OK는 항상 계산 결과로만 나오고, "SSOT_*_OK=1" 같은 문자열을 직접 박아두면 실패 처리.

ROOT="webcore_appcore_starter_4_17"
TARGET_DIRS=(
  "$ROOT/scripts/verify"
  "$ROOT/scripts/ops"
)

# ripgrep가 없을 수 있으니 grep로도 동작하도록 구성
found=0

for d in "${TARGET_DIRS[@]}"; do
  [ -d "$d" ] || continue

  # 직접적인 하드코딩 패턴 탐지(예: echo "SSOT_XXX_OK=1")
  if command -v rg >/dev/null 2>&1; then
    if rg -n --hidden --no-ignore -S 'SSOT_[A-Z0-9_]+_OK=1' "$d" 2>/dev/null; then
      found=1
    fi
    if rg -n --hidden --no-ignore -S 'printf\("SSOT_[A-Z0-9_]+_OK=1\\n"\)' "$d" 2>/dev/null; then
      found=1
    fi
  else
    if grep -RIn 'S
fi

echo "PASS: No unconditional OK=1 patterns found"
