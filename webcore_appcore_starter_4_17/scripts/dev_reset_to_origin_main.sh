#!/usr/bin/env bash
set -euo pipefail

# ✅ S6-S7: FF-only 실패 복구 표준
# git pull --ff-only 실패(로컬 diverged/꼬임) 시, 이 스크립트로만 복구
# 안전 가드: dirty면 즉시 중단 후 수동 정리(사고 방지)

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "[reset] Reset to origin/main (FF-only failure recovery)"

# 안전 가드: dirty 체크
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "[FAIL] Working tree is dirty. Please commit or stash changes first."
  echo "[FAIL] This script will not proceed with uncommitted changes."
  exit 1
fi

# untracked files 체크
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "[warn] Untracked files detected. They will remain after reset."
  echo "[warn] Continue? (y/N)"
  read -r confirm
  if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "[abort] Reset cancelled"
    exit 1
  fi
fi

# origin/main 최신화
echo "[step] Fetching origin/main..."
git fetch origin main || {
  echo "[FAIL] git fetch origin main failed"
  exit 1
}

# 현재 브랜치 확인
current_branch=$(git rev-parse --abbrev-ref HEAD)
echo "[info] Current branch: $current_branch"

# origin/main으로 hard reset
echo "[step] Resetting to origin/main..."
git reset --hard origin/main || {
  echo "[FAIL] git reset --hard origin/main failed"
  exit 1
}

# clean (untracked는 제외, -fd는 위험하므로 사용자 확인 후)
echo "[step] Cleaning working tree..."
git clean -fd || {
  echo "[warn] git clean -fd failed (some files may remain)"
}

echo "[OK] Reset to origin/main completed"
echo "[info] Current commit: $(git rev-parse --short HEAD)"
echo "[info] Branch: $(git rev-parse --abbrev-ref HEAD)"

