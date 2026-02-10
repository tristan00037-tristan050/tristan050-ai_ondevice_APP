#!/usr/bin/env bash
set -euo pipefail

VERIFY_NO_RIPGREP_IN_VERIFY_OK=0

cleanup() {
  echo "VERIFY_NO_RIPGREP_IN_VERIFY_OK=${VERIFY_NO_RIPGREP_IN_VERIFY_OK}"
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# verify 스크립트 내부에서 rg/ ripgrep 호출 금지 (도구 편차 차단)
# 원문 덤프 금지: 경로만 출력
# 자기 자신 제외 (이 스크립트는 검사 대상이 아님)
HIT="$(grep -RIn --exclude-dir=node_modules --exclude='*.md' --exclude='*.txt' --exclude='*.json' \
  --exclude='verify_no_ripgrep_in_verify_v1.sh' \
  -E '(^|[[:space:]])(rg|ripgrep)([[:space:]]|$)' scripts/verify webcore_appcore_starter_4_17/scripts/verify 2>/dev/null || true)"

if [[ -n "${HIT}" ]]; then
  echo "BLOCK: ripgrep usage detected in verify scripts"
  echo "${HIT}" | cut -d: -f1 | sort -u | head -200
  exit 1
fi

VERIFY_NO_RIPGREP_IN_VERIFY_OK=1
exit 0

