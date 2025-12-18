#!/usr/bin/env bash
set -euo pipefail

PORT=8081
echo "[dev_bff] Freeing port ${PORT}..."
PID="$(lsof -nP -tiTCP:${PORT} -sTCP:LISTEN || true)"
if [ -n "${PID}" ]; then
  echo "[dev_bff] Killing PID(s): ${PID}"
  kill -15 ${PID} || true
  sleep 1
  kill -9 ${PID} || true
fi

export USE_PG=1
export EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-dev-export-secret}"
export DATABASE_URL="${DATABASE_URL:-postgres://app:app@127.0.0.1:5432/app}"

echo "[dev_bff] Starting BFF on :${PORT}"
npm run dev:bff
