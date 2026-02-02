#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?MODE required}"
SEED="${2:?SEED required}"

# 현재 레포에서 알고리즘 엔트리가 확정되기 전까지는,
# "결정론 게이트 출력 계약"만 먼저 고정한다.
# 후속 PR에서 실제 알고리즘 실행을 연결한다.

# meta-only 출력(원문 금지)
echo "DETERMINISM_MODE=${MODE}"

# 임시 체크섬: 현재는 정책/환경 문자열에 대한 sha256.
# 후속 PR에서 실제 모델 출력 텐서/결과를 해시로 바꾼다.
printf "%s" "mode=${MODE};seed=${SEED};node=$(node -v 2>/dev/null || echo none)" | sha256sum | awk '{print "DETERMINISM_SHA256="$1}'

