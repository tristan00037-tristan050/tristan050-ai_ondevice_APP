#!/usr/bin/env bash
set -euo pipefail

# meta-only: 키/에러코드만 출력
RUN_GUARD_TARGETS_EXIST_OK=0
trap 'echo "RUN_GUARD_TARGETS_EXIST_OK=${RUN_GUARD_TARGETS_EXIST_OK}"' EXIT

ANCHOR="scripts/verify/verify_repo_contracts.sh"
if [ ! -f "$ANCHOR" ]; then
  echo "ERROR_CODE=RUN_GUARD_ANCHOR_MISSING"
  echo "HIT_PATH=$ANCHOR"
  exit 1
fi

missing=0
unparseable=0

# run_guard 라인 중 ' bash ' 다음 토큰을 스크립트 경로로 취급
# 예: run_guard "name" bash scripts/verify/verify_xxx.sh
# 주의: meta-only 원칙에 따라 원문 라인은 출력하지 않음
while IFS= read -r line; do
  case "$line" in
    *run_guard*" bash "*)
      # bash 다음 필드 추출(공백 기준). 따옴표는 제거.
      path="$(printf "%s\n" "$line" | awk '{
        for(i=1;i<=NF;i++){
          if($i=="bash"){
            print $(i+1);
            exit
          }
        }
      }')"

      # 파싱 실패는 fail-closed
      if [ -z "${path:-}" ]; then
        echo "ERROR_CODE=RUN_GUARD_UNPARSEABLE"
        unparseable=1
        continue
      fi

      # 따옴표/뒤따르는 기호 정리(최소)
      path="${path%\"}"; path="${path#\"}"
      path="${path%\'}"; path="${path#\'}"
      # 경로 뒤에 붙는 ';' 또는 '&&' 같은 토큰을 최소 컷
      path="${path%%;*}"
      path="${path%%&&*}"

      if [ ! -f "$path" ]; then
        echo "ERROR_CODE=RUN_GUARD_TARGET_MISSING"
        echo "HIT_PATH=$path"
        missing=1
      fi
      ;;
  esac
done < "$ANCHOR"

if [ "$unparseable" -ne 0 ]; then
  exit 1
fi
if [ "$missing" -ne 0 ]; then
  exit 1
fi

RUN_GUARD_TARGETS_EXIST_OK=1
exit 0
