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
# ✅ R10-S4: 기본값 설정 (로컬 개발용)
export WEBLLM_UPSTREAM_BASE_URL="${WEBLLM_UPSTREAM_BASE_URL:-http://127.0.0.1:9099/webllm/}"

# --- BEGIN: dist freshness guard (S6-4 baseline hardening) ---
ensure_bff_dist_fresh() {
  local ROOT
  ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

  local PKG="$ROOT/packages/bff-accounting"
  local DIST="$PKG/dist/index.js"

  if [ ! -f "$DIST" ]; then
    echo "[dev_bff] dist missing -> build @appcore/bff-accounting"
    npm run -w @appcore/bff-accounting build
    return 0
  fi

  # src나 설정이 dist보다 새로우면 build
  if find "$PKG/src" -type f \( -name "*.ts" -o -name "*.tsx" \) -newer "$DIST" | head -n 1 | grep -q .; then
    echo "[dev_bff] src newer than dist -> build @appcore/bff-accounting"
    npm run -w @appcore/bff-accounting build
    return 0
  fi

  if [ "$PKG/tsconfig.json" -nt "$DIST" ] || [ "$PKG/tsconfig.build.json" -nt "$DIST" ] || [ "$PKG/package.json" -nt "$DIST" ]; then
    echo "[dev_bff] config newer than dist -> build @appcore/bff-accounting"
    npm run -w @appcore/bff-accounting build
    return 0
  fi

  echo "[dev_bff] dist is fresh (skip build)"
}

# BFF 시작 전에 반드시 호출
ensure_bff_dist_fresh
# --- END: dist freshness guard ---

echo "[dev_bff] Starting BFF on :${PORT}"
echo "[dev_bff] DATABASE_URL=${DATABASE_URL}"
echo "[dev_bff] WEBLLM_UPSTREAM_BASE_URL=${WEBLLM_UPSTREAM_BASE_URL}"
npm run dev:bff
