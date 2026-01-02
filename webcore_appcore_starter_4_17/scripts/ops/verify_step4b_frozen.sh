#!/usr/bin/env bash
set -euo pipefail

# Step4-B Frozen Improvement Protocol 검증
# 목적: 입력/베이스라인 변경을 코드로 즉시 차단

# 레포 루트로 이동 (경로 일관성 강제)
cd "$(git rev-parse --show-toplevel)"

BASE_REF="${BASE_REF:-origin/main}"

# BASE_REF 최신화 강제 (fetch 실패 시 exit 1)
git fetch -q origin main:refs/remotes/origin/main || {
  echo "FAIL: cannot fetch origin/main (BASE_REF=$BASE_REF)" >&2
  exit 1
}

# 변경 파일 목록 수집 (committed + staged + worktree, 중복 제거)
# 1) committed changes (BASE_REF...HEAD)
COMMITTED="$(git diff --name-only "$BASE_REF"...HEAD 2>/dev/null || echo "")"

# 2) staged changes
STAGED="$(git diff --cached --name-only 2>/dev/null || echo "")"

# 3) worktree changes
WORKTREE="$(git diff --name-only 2>/dev/null || echo "")"

# 중복 제거하여 병합
CHANGED_FILES="$(echo -e "$COMMITTED\n$STAGED\n$WORKTREE" | grep -v '^$' | sort -u)"

if [ -z "$CHANGED_FILES" ]; then
  echo "OK: no changes detected (frozen protocol satisfied)"
  exit 0
fi

# 금지 경로 패턴 (메타-only: 경로만 검사, 원문 출력 금지)
FORBIDDEN_PATTERNS=(
  "docs/ops/r10-s7-retriever-metrics-baseline.json"
  "docs/ops/r10-s7-retriever-corpus.jsonl"
  "docs/ops/r10-s7-retriever-goldenset.jsonl"
  "tools/step4a/build_retriever_corpus"
  "scripts/ops/verify_s7_corpus_no_pii.sh"
  "scripts/ops/verify_rag_meta_only.sh"
)

VIOLATIONS=()

while IFS= read -r file; do
  [ -z "$file" ] && continue
  
  # 경로 정규화: webcore_appcore_starter_4_17/ prefix 제거 (레포 루트 기준 상대 경로)
  normalized_file="${file#webcore_appcore_starter_4_17/}"
  # prefix가 없으면 그대로 사용
  if [ "$normalized_file" = "$file" ]; then
    normalized_file="$file"
  fi
  
  for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if echo "$normalized_file" | grep -q "$pattern"; then
      VIOLATIONS+=("$file")
      break
    fi
  done
done <<< "$CHANGED_FILES"

if [ ${#VIOLATIONS[@]} -gt 0 ]; then
  echo "FAIL: Step4-B Frozen Improvement Protocol violation detected" >&2
  echo "BASE_REF=$BASE_REF" >&2
  echo "Violated files (meta-only, paths only):" >&2
  for v in "${VIOLATIONS[@]}"; do
    echo "  - $v" >&2
  done
  echo "Rule: baseline.json, corpus.jsonl, goldenset.jsonl, corpus builder, PII/meta-only verifiers must not be modified in Step4-B" >&2
  exit 1
fi

echo "OK: Step4-B Frozen Improvement Protocol satisfied"
echo "BASE_REF=$BASE_REF"
echo "Changed files count: $(echo "$CHANGED_FILES" | grep -c . || echo 0)"
exit 0
