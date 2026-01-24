#!/usr/bin/env bash
set -euo pipefail

NO_LOG_GREP_VERDICT_OK=0
cleanup(){ echo "NO_LOG_GREP_VERDICT_OK=${NO_LOG_GREP_VERDICT_OK}"; }
trap cleanup EXIT

# 판정에 쓰이는 log-grep 패턴 금지 (문장/로그 기반 verdict 차단)
# 금지: TEST_OUTPUT 변수를 grep해서 테스트 결과 판정하는 패턴
# 허용: grep -q "$VAR" (일반 검사용), PATTERN= 정의 라인
PATTERN='TEST_OUTPUT.*grep'

HITS="$(rg -n "$PATTERN" webcore_appcore_starter_4_17/scripts/verify scripts/verify 2>/dev/null | grep -v 'PATTERN=' | grep -v 'verify_no_log_grep_verdict.sh' || true)"
if [[ -n "$HITS" ]]; then
  echo "FAIL: log-grep verdict patterns found"
  echo "$HITS"
  exit 1
fi

NO_LOG_GREP_VERDICT_OK=1
exit 0

