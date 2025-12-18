#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_ports.sh"

MODE="${1:-up}"   # up | restart
PORT=8081

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

if [ "${MODE}" = "up" ]; then
  if bff_is_healthy; then
    echo "[dev_bff] BFF already healthy on :${PORT} (skip restart)"
    exit 0
  fi
fi

echo "[dev_bff] Freeing port ${PORT}..."
free_port_strict "${PORT}"

# restart 모드일 때는 빌드 후 실행 (src 수정 ↔ dist 실행 불일치 방지)
if [ "${MODE}" = "restart" ]; then
  echo "[dev_bff] Building bff-accounting..."
  npm run -w @appcore/bff-accounting build || npm run build --workspace=@appcore/bff-accounting
fi

echo "[dev_bff] Starting BFF on :${PORT}"
export USE_PG="${USE_PG:-1}"
export EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-dev-export-secret}"
export DATABASE_URL="${DATABASE_URL:-postgres://app:app@127.0.0.1:5432/app}"

npm run dev:bff
