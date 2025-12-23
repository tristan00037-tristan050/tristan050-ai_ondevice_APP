#!/usr/bin/env bash
set -euo pipefail

PORT="${WEBLLM_UPSTREAM_SERVER_PORT:-9099}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${WEBLLM_UPSTREAM_DIR:-$ROOT/tools/webllm_upstream}"

echo "[webllm-upstream] Freeing port ${PORT}..."
PIDS="$(lsof -nP -tiTCP:${PORT} -sTCP:LISTEN || true)"
if [ -n "${PIDS}" ]; then
  echo "[webllm-upstream] Killing PID(s): ${PIDS}"
  kill -15 ${PIDS} 2>/dev/null || true
  sleep 1
  kill -9 ${PIDS} 2>/dev/null || true
fi

export WEBLLM_UPSTREAM_SERVER_PORT="${PORT}"
export WEBLLM_UPSTREAM_DIR="${DIR}"

# 업스트림 서버가 없으면 SKIP
if [ ! -f "$ROOT/scripts/webllm_upstream_server.mjs" ]; then
  echo "[webllm-upstream] WARN: webllm_upstream_server.mjs not found, skipping upstream server"
  echo "[webllm-upstream] INFO: verify_range_206.sh will skip tests if upstream is not available"
  exit 0
fi

echo "[webllm-upstream] WEBLLM_UPSTREAM_SERVER_PORT=${PORT}"
echo "[webllm-upstream] WEBLLM_UPSTREAM_DIR=${DIR}"
echo "[webllm-upstream] starting..."
node "$ROOT/scripts/webllm_upstream_server.mjs"

