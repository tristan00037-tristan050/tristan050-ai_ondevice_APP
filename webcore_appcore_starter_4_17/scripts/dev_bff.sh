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

# DB env (빈 문자열이어도 기본값 적용되도록 :- 사용)
export USE_PG=1
export EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-dev-export-secret}"
export DATABASE_URL="${DATABASE_URL:-postgres://app:app@127.0.0.1:5432/app}"

# pg 라이브러리가 DATABASE_URL 대신 개별 환경변수를 읽는 케이스까지 대비
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-app}"
export PGPASSWORD="${PGPASSWORD:-app}"
export PGDATABASE="${PGDATABASE:-app}"

# 안전 체크: DATABASE_URL이 비어있거나 형식이 이상하면 즉시 중단(재발 방지 핵심)
if [ -z "${DATABASE_URL}" ] || [[ "${DATABASE_URL}" != *"://"* ]]; then
  echo "[dev_bff] ERROR: DATABASE_URL is empty/invalid. (got: '${DATABASE_URL}')"
  echo "[dev_bff] Fix: export DATABASE_URL='postgres://app:app@127.0.0.1:5432/app'"
  exit 1
fi

echo "[dev_bff] Starting BFF on :${PORT}"
echo "[dev_bff] DATABASE_URL=${DATABASE_URL}"
npm run dev:bff
