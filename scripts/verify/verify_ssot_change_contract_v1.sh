#!/usr/bin/env bash
set -euo pipefail

SSOT_CHANGE_CONTRACT_V1_OK=0
finish(){ echo "SSOT_CHANGE_CONTRACT_V1_OK=${SSOT_CHANGE_CONTRACT_V1_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 감시 대상 SSOT(최소 세트, add-only 확장)
SSOT_FILES=(
  "docs/ops/contracts/OUTPUT_ROOT_SSOT_V1.txt"
  "docs/ops/contracts/EXEC_MODE_SCHEMA_V1.json"
)

# required guard 이름(실제 실행 라인 존재를 강제)
required_guards=(
  "output root ssot v1"
  "exec-mode schema ssot consumed v1"
)

# 1) 먼저: HEAD 커밋 자체가 SSOT 파일을 건드렸는지 빠른 체크(베이스 없어도 0-impact 판단 가능)
#    - HEAD에서 SSOT 파일 변경이 전혀 없으면 PASS (계약: non-SSOT change는 0-impact)
touched_head=0
for f in "${SSOT_FILES[@]}"; do
  if git show --name-only --pretty=format: HEAD -- "$f" | grep -q .; then
    touched_head=1
    break
  fi
done

if [ "$touched_head" = "0" ]; then
  SSOT_CHANGE_CONTRACT_V1_OK=1
  exit 0
fi

# 2) 여기부터는 "SSOT가 변경된 PR일 가능성" → base sha 확보 후 PR 전체 범위에서 변경 여부를 확정
BASE_SHA=""
if [ -n "${GITHUB_EVENT_PATH:-}" ] && [ -f "${GITHUB_EVENT_PATH:-}" ]; then
  # GitHub Actions PR 이벤트에서 base.sha 추출
  BASE_SHA="$(node -e 'const fs=require("fs"); const j=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); const sha=j.pull_request && j.pull_request.base && j.pull_request.base.sha; if(sha) process.stdout.write(sha);' "$GITHUB_EVENT_PATH" 2>/dev/null)" || true
fi

BASE_REF="${SSOT_CONTRACT_BASE_REF:-origin/main}"

# base sha가 있으면 그 sha를 fetch해서 diff 근거를 확정(얕은 체크아웃에서도 안전)
if [ -n "$BASE_SHA" ]; then
  git fetch --no-tags --depth=1 origin "$BASE_SHA" >/dev/null 2>&1 || true
fi

# base ref/sha가 실제로 존재하는지 확인
if [ -n "$BASE_SHA" ] && git rev-parse --verify "$BASE_SHA" >/dev/null 2>&1; then
  base="$BASE_SHA"
elif git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  base="$BASE_REF"
else
  # SSOT 변경이 감지된 상황에서만 fail-closed
  echo "ERROR_CODE=BASE_REF_MISSING_FOR_SSOT_CHANGE"
  exit 1
fi

# PR 전체 범위에서 SSOT 변경이 실제로 있는지 확정
changed=0
for f in "${SSOT_FILES[@]}"; do
  if git diff --name-only "$base"...HEAD -- "$f" | grep -q .; then
    changed=1
    break
  fi
done

# 실제로 SSOT 변경이 아니면 PASS(0-impact 유지)
if [ "$changed" = "0" ]; then
  SSOT_CHANGE_CONTRACT_V1_OK=1
  exit 0
fi

# 3) SSOT 변경이 실제로 있음 → required guard가 "실제로 실행"되도록 verify_repo_contracts.sh에서 확인
missing=0
for g in "${required_guards[@]}"; do
  # 주석/죽은 텍스트 제외: 실제 run_guard 실행 라인만 인정
  if ! grep -Eq "^[[:space:]]*run_guard[[:space:]]+\"${g}\"[[:space:]]+" scripts/verify/verify_repo_contracts.sh; then
    echo "ERROR_CODE=MISSING_REQUIRED_GUARD"
    echo "MISSING_GUARD=${g}"
    missing=1
  fi
done
[ "$missing" = "0" ] || exit 1

SSOT_CHANGE_CONTRACT_V1_OK=1
exit 0
