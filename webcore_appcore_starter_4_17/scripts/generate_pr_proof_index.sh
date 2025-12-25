#!/usr/bin/env bash
set -euo pipefail

# ✅ S6-S7: PR 증빙 인덱스 자동 생성
# 이번 PR에서 변경된 docs/ops proof 목록 + 체크섬을 자동 생성
# PR 코멘트에 붙여 넣어 "이번 PR이 무엇을 봉인했는지"를 자동 증빙

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

# base 브랜치 (기본값: main)
BASE_BRANCH="${1:-main}"

OPS_DIR="$ROOT/docs/ops"
TMP_INDEX="$(mktemp -t pr_proof_index.XXXXXX)"

echo "[generate] PR Proof Index"
echo "[info] base: $BASE_BRANCH"

# base 브랜치와 현재 브랜치의 diff에서 docs/ops 파일만 추출
changed_files=$(git diff --name-only "$BASE_BRANCH" HEAD -- "$OPS_DIR" 2>/dev/null || echo "")

if [ -z "$changed_files" ]; then
  echo "[info] no docs/ops files changed in this PR"
  exit 0
fi

echo ""
echo "## 📋 PR Proof Index"
echo ""
echo "### Changed Proof Files"
echo ""

proof_count=0
proof_files=()

while IFS= read -r file; do
  if [ -z "$file" ]; then
    continue
  fi
  
  file_path="$ROOT/$file"
  if [ ! -f "$file_path" ]; then
    continue
  fi
  
  # docs/ops 내 파일만 처리
  if [[ "$file" =~ ^webcore_appcore_starter_4_17/docs/ops/ ]]; then
    proof_count=$((proof_count + 1))
    proof_files+=("$file")
    
    # 파일명 (상대 경로)
    rel_path="${file#webcore_appcore_starter_4_17/}"
    
    # 체크섬 계산
    if command -v shasum >/dev/null 2>&1; then
      checksum=$(shasum -a 256 "$file_path" | cut -d' ' -f1)
    elif command -v sha256sum >/dev/null 2>&1; then
      checksum=$(sha256sum "$file_path" | cut -d' ' -f1)
    else
      checksum="(no sha256 command)"
    fi
    
    # 파일 크기
    file_size=$(stat -f "%z" "$file_path" 2>/dev/null || stat -c "%s" "$file_path" 2>/dev/null || echo "0")
    
    echo "- **$rel_path**"
    echo "  - SHA256: \`$checksum\`"
    echo "  - Size: $file_size bytes"
    echo ""
  fi
done <<< "$changed_files"

if [ $proof_count -eq 0 ]; then
  echo "[info] no proof files found in changes"
  exit 0
fi

echo "### Summary"
echo ""
echo "- **Total Proof Files**: $proof_count"
echo "- **Base Branch**: \`$BASE_BRANCH\`"
echo "- **Current Commit**: \`$(git rev-parse --short HEAD)\`"
echo ""

# 체크섬 목록 (검증용)
echo "### Checksums (Verification)"
echo ""
echo "\`\`\`"
for file in "${proof_files[@]}"; do
  file_path="$ROOT/$file"
  if [ -f "$file_path" ]; then
    if command -v shasum >/dev/null 2>&1; then
      checksum=$(shasum -a 256 "$file_path" | cut -d' ' -f1)
    elif command -v sha256sum >/dev/null 2>&1; then
      checksum=$(sha256sum "$file_path" | cut -d' ' -f1)
    else
      checksum="(no sha256 command)"
    fi
    rel_path="${file#webcore_appcore_starter_4_17/}"
    echo "$checksum  $rel_path"
  fi
done
echo "\`\`\`"
echo ""

rm -f "$TMP_INDEX"

