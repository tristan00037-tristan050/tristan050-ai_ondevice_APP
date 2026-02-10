#!/usr/bin/env bash
set -euo pipefail

VERIFY_NO_DEV_TCP_IN_VERIFY_OK=0

cleanup() { echo "VERIFY_NO_DEV_TCP_IN_VERIFY_OK=${VERIFY_NO_DEV_TCP_IN_VERIFY_OK}"; }
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 자기 자신 제외 (이 스크립트는 검사 대상이 아님)
# 주석/echo/문자열 리터럴 내의 '/dev/tcp'는 제외하고, 실제 코드 사용만 검사
# 패턴: echo/주석이 아닌 줄에서 '/dev/tcp' 사용 (실제 코드 경로)
HIT="$(grep -RIn --exclude-dir=node_modules --exclude='*.md' --exclude='*.txt' --exclude='*.json' \
  --exclude='verify_no_dev_tcp_in_verify_v1.sh' \
  scripts/verify webcore_appcore_starter_4_17/scripts/verify 2>/dev/null | \
  grep -vE '^[^:]*:[^:]*:(echo|#|run_guard|== guard)' | \
  grep -E '/dev/tcp' || true)"

if [[ -n "${HIT}" ]]; then
  echo "BLOCK: /dev/tcp usage detected in verify scripts"
  echo "${HIT}" | cut -d: -f1 | sort -u | head -200
  exit 1
fi

VERIFY_NO_DEV_TCP_IN_VERIFY_OK=1
exit 0

