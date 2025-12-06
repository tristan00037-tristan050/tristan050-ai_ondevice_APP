#!/bin/bash
# Docker Compose를 통한 psql 래퍼 스크립트
# 사용법: ./scripts/psql.sh -c "SELECT * FROM ..."
# 또는: ./scripts/psql.sh (대화형 세션)

cd "$(dirname "$0")/.."
docker compose exec db psql -U app -d app "$@"

