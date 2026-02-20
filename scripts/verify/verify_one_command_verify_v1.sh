#!/usr/bin/env bash
set -euo pipefail

ONE_COMMAND_VERIFY_V1_OK=0
trap 'echo "ONE_COMMAND_VERIFY_V1_OK=$ONE_COMMAND_VERIFY_V1_OK"' EXIT

script="tools/verify_one_v1.sh"
test -f "$script" || { echo "BLOCK: missing $script"; exit 1; }
test -x "$script" || { echo "BLOCK: $script must be executable"; exit 1; }

# 주석/공백 제거한 "실제 명령 라인"에서만 매칭한다.
# - 라인 시작이 bash 로 시작하고
# - 정확히 목표 커맨드와 일치할 때만 인정한다.
preflight_line=""
verify_line=""
lineno=0

while IFS= read -r raw || [ -n "$raw" ]; do
  lineno=$((lineno+1))

  # 1) 앞뒤 공백 제거
  line="$(echo "$raw" | awk '{$1=$1;print}')"

  # 2) 빈줄/주석줄 제거
  [ -z "$line" ] && continue
  case "$line" in
    \#*) continue ;;
  esac

  # 3) 라인 끝 주석 제거 (단, 매우 단순 규칙: # 이후는 주석으로 취급)
  #    운영 규율상 verify_one_v1.sh는 복잡한 쉘 구문을 쓰지 않는 것이 맞습니다.
  line="${line%%#*}"
  line="$(echo "$line" | awk '{$1=$1;print}')"
  [ -z "$line" ] && continue

  # 4) 정확히 일치하는 실행 라인만 인정
  if [ -z "$preflight_line" ] && [ "$line" = "bash tools/preflight_v1.sh" ]; then
    preflight_line="$lineno"
    continue
  fi

  if [ -z "$verify_line" ] && [ "$line" = "bash scripts/verify/verify_repo_contracts.sh ; echo \"EXIT=\$?\"" ]; then
    verify_line="$lineno"
    continue
  fi
  if [ -z "$verify_line" ] && [ "$line" = "bash scripts/verify/verify_repo_contracts.sh; echo \"EXIT=\$?\"" ]; then
    verify_line="$lineno"
    continue
  fi
  if [ -z "$verify_line" ] && [ "$line" = "bash scripts/verify/verify_repo_contracts.sh" ]; then
    # echo EXIT는 verify_one_v1.sh 내부에서 안 할 수도 있으므로 허용
    verify_line="$lineno"
    continue
  fi
done < "$script"

[ -n "$preflight_line" ] || { echo "BLOCK: missing real command line: bash tools/preflight_v1.sh"; exit 1; }
[ -n "$verify_line" ] || { echo "BLOCK: missing real command line: bash scripts/verify/verify_repo_contracts.sh"; exit 1; }

# 순서 강제
[ "$preflight_line" -lt "$verify_line" ] || { echo "BLOCK: preflight must run before verify (real command lines)"; exit 1; }

ONE_COMMAND_VERIFY_V1_OK=1
exit 0
