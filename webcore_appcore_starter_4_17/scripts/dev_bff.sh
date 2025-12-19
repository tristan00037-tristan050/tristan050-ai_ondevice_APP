#!/usr/bin/env bash
set -euo pipefail

PORT=8081

echo "[dev_bff] Freeing port ${PORT}..."
for i in 1 2 3 4 5; do
  PIDS="$(lsof -nP -tiTCP:${PORT} -sTCP:LISTEN || true)"
  if [ -z "${PIDS}" ]; then
    break
  fi
  echo "[dev_bff] Attempt ${i}: killing PID(s): ${PIDS}"
  kill -15 ${PIDS} 2>/dev/null || true
  sleep 0.3
  kill -9 ${PIDS} 2>/dev/null || true
  sleep 0.3
done

# 최종 확인
PIDS="$(lsof -nP -tiTCP:${PORT} -sTCP:LISTEN || true)"
if [ -n "${PIDS}" ]; then
  echo "[dev_bff] ERROR: port ${PORT} still in use by PID(s): ${PIDS}"
  lsof -nP -iTCP:${PORT} -sTCP:LISTEN || true
  exit 1
fi

# --- DB env ---
export USE_PG=1
export EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-dev-export-secret}"
export DATABASE_URL="${DATABASE_URL:-postgres://app:app@127.0.0.1:5432/app}"

export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-app}"
export PGPASSWORD="${PGPASSWORD:-app}"
export PGDATABASE="${PGDATABASE:-app}"

if [ -z "${DATABASE_URL}" ] || [[ "${DATABASE_URL}" != *"://"* ]]; then
  echo "[dev_bff] ERROR: DATABASE_URL is empty/invalid. (got: '${DATABASE_URL}')"
  exit 1
fi

# --- Model proxy upstream ---
export WEBLLM_UPSTREAM_BASE_URL="${WEBLLM_UPSTREAM_BASE_URL:-http://127.0.0.1:9099/webllm/}"

echo "[dev_bff] Starting BFF on :${PORT}"
echo "[dev_bff] DATABASE_URL=${DATABASE_URL}"
echo "[dev_bff] WEBLLM_UPSTREAM_BASE_URL=${WEBLLM_UPSTREAM_BASE_URL}"

# === WEBLLM UPSTREAM STANDARD v1 (FAIL-CLOSED) ===
# 팀 표준:
# - WEBLLM_UPSTREAM_BASE_URL은 반드시 "/"로 끝나야 함
# - http(s):// 로 시작해야 함
# - dev_check가 항상 존재하는 probe 파일로 자동검증 가능해야 함
#
# 기본값(로컬 dev): http://127.0.0.1:9099/webllm/
export WEBLLM_UPSTREAM_BASE_URL="${WEBLLM_UPSTREAM_BASE_URL:-http://127.0.0.1:9099/webllm/}"

# fail-closed: 빈 값/형식 오류 즉시 차단
if [ -z "${WEBLLM_UPSTREAM_BASE_URL}" ]; then
  echo "[dev_bff] ERROR: WEBLLM_UPSTREAM_BASE_URL is empty"
  echo "[dev_bff] Fix: export WEBLLM_UPSTREAM_BASE_URL='http://127.0.0.1:9099/webllm/'"
  exit 1
fi

case "${WEBLLM_UPSTREAM_BASE_URL}" in
  http://*|https://*) ;;
  *)
    echo "[dev_bff] ERROR: WEBLLM_UPSTREAM_BASE_URL must start with http:// or https://"
    echo "[dev_bff] Got: ${WEBLLM_UPSTREAM_BASE_URL}"
    exit 1
    ;;
esac

case "${WEBLLM_UPSTREAM_BASE_URL}" in
  */) ;;
  *)
    echo "[dev_bff] ERROR: WEBLLM_UPSTREAM_BASE_URL must end with '/' (trailing slash required)"
    echo "[dev_bff] Got: ${WEBLLM_UPSTREAM_BASE_URL}"
    exit 1
    ;;
esac

echo "[dev_bff] WEBLLM_UPSTREAM_BASE_URL=${WEBLLM_UPSTREAM_BASE_URL}"

npm run dev:bff
