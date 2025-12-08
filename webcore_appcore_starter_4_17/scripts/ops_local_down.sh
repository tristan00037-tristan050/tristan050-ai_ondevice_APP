#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "=== [ops_local_down] 로컬 Docker 종료 ==="

docker compose down

echo "모든 컨테이너를 종료했습니다."

