#!/usr/bin/env bash
# 푸시가 성공한 뒤 로컬에서 실행하세요.
# 사용법: cd "$(git rev-parse --show-toplevel)" && git switch pr/p24-sc2-01-butler-workspace-v1 && bash scripts/ops/PR_P24_SC2_01_푸시후_실행.sh

set -e
cd "$(git rev-parse --show-toplevel)"
CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" != "pr/p24-sc2-01-butler-workspace-v1" ]]; then
  echo "현재 브랜치가 pr/p24-sc2-01-butler-workspace-v1 이 아닙니다: $CURRENT_BRANCH"
  exit 1
fi

echo "푸시 시도..."
git push -u origin "$CURRENT_BRANCH"

if command -v gh >/dev/null 2>&1; then
  echo "PR 생성..."
  gh pr create \
    --base main \
    --head "$CURRENT_BRANCH" \
    --title "P24-SC2-01: Butler 본체 정의 반영 + 운영판/본체 분리 UI 추가" \
    --body-file .pr-body-p24-sc2-01.txt
else
  echo "gh 미설치. 아래 URL에서 수동으로 PR 생성:"
  echo "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/compare/main...${CURRENT_BRANCH}?expand=1"
fi
