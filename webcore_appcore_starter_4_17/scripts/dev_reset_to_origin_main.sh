#!/usr/bin/env bash
set -euo pipefail

# ✅ S6-S7: FF-only 실패 복구 표준
# git pull --ff-only 실패(로컬 diverged/꼬임) 시, 이 스크립트로만 복구
# 안전 가드: dirty면 즉시 중단 후 수동 정리(사고 방지)

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 명시 플래그 체크
FORCE_FLAG="${1:-}"

echo "[reset] Reset to origin/main (FF-only failure recovery)"

# ✅ 하드 룰: dirty면 즉시 종료
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "[FAIL] Working tree is dirty. Please commit or stash changes first."
  echo "[FAIL] This script will not proceed with uncommitted changes."
  exit 1
fi

# untracked files 체크 및 삭제 대상 프리뷰
untracked=$(git ls-files --others --exclude-standard)
if [ -n "$untracked" ]; then
  echo "[warn] Untracked files detected:"
  echo "$untracked" | head -20
  if [ "$(echo "$untracked" | wc -l)" -gt 20 ]; then
    echo "... (and more)"
  fi
  
  # ✅ 하드 룰: 명시 플래그 없으면 실행 금지 또는 프리뷰 후 중단
  if [ "$FORCE_FLAG" != "--force" ] && [ "$FORCE_FLAG" != "--i-know-what-im-doing" ]; then
    echo "[FAIL] Use --force or --i-know-what-im-doing to proceed with untracked files"
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

# ✅ 하드 룰: reset/clean은 명시 플래그 없으면 실행 금지 또는 프리뷰 후 중단
if [ "$FORCE_FLAG" != "--force" ] && [ "$FORCE_FLAG" != "--i-know-what-im-doing" ]; then
  echo "[preview] Would reset to origin/main and clean untracked files"
  echo "[preview] Use --force or --i-know-what-im-doing to proceed"
  exit 0
fi

# origin/main으로 hard reset
echo "[step] Resetting to origin/main..."
git reset --hard origin/main || {
  echo "[FAIL] git reset --hard origin/main failed"
  exit 1
}

# ✅ 하드 룰: 보호 목록(.env, secrets, docs/ops 등)은 clean 제외(allowlist 방식)
# clean 대상에서 제외할 파일/디렉토리
PROTECTED_PATTERNS=(
  ".env"
  ".env.*"
  "**/secrets/**"
  "**/docs/ops/**"
  "**/*.secret"
  "**/*.key"
)

# clean 실행 (보호 목록 제외)
echo "[step] Cleaning working tree (protected files excluded)..."
if [ -n "$untracked" ]; then
  # 보호 목록에 해당하지 않는 파일만 삭제
  while IFS= read -r file; do
    [ -z "$file" ] && continue
    
    # 보호 목록 체크
    should_protect=false
    for pattern in "${PROTECTED_PATTERNS[@]}"; do
      if [[ "$file" == $pattern ]] || [[ "$file" == */$pattern ]] || [[ "$file" == $pattern/* ]]; then
        should_protect=true
        break
      fi
    done
    
    if [ "$should_protect" = false ]; then
      rm -rf "$file" 2>/dev/null || true
    else
      echo "[protect] Skipping protected file: $file"
    fi
  done <<< "$untracked"
fi

echo "[OK] Reset to origin/main completed"
echo "[info] Current commit: $(git rev-parse --short HEAD)"
echo "[info] Branch: $(git rev-parse --abbrev-ref HEAD)"

