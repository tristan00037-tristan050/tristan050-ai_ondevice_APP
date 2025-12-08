#!/bin/bash
# Docker Compose를 통한 psql 래퍼 스크립트
# 사용법: ./scripts/psql.sh -c "SELECT * FROM ..."
# 또는: ./scripts/psql.sh (대화형 세션)
# 또는: ./scripts/psql.sh -f scripts/check_audit_events.sql

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# -f 옵션이 있으면 파일을 컨테이너에 복사해서 실행
if [[ "$1" == "-f" && -n "$2" ]]; then
  FILE_PATH="$2"
  ABS_FILE_PATH="$(cd "$(dirname "$FILE_PATH")" && pwd)/$(basename "$FILE_PATH")"
  FILE_NAME="$(basename "$FILE_PATH")"
  
  # 파일을 컨테이너에 복사
  docker compose cp "$ABS_FILE_PATH" db:/tmp/"$FILE_NAME"
  
  # 컨테이너 내부에서 실행
  docker compose exec db psql -U app -d app -f /tmp/"$FILE_NAME"
  
  # 임시 파일 삭제
  docker compose exec db rm /tmp/"$FILE_NAME"
else
  # 일반 쿼리 실행
  docker compose exec db psql -U app -d app "$@"
fi

