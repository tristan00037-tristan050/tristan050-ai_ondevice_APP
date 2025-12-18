#!/usr/bin/env bash
set -euo pipefail

WEB_PORT=8083
echo "[dev_web] Freeing port ${WEB_PORT}..."
PID="$(lsof -nP -tiTCP:${WEB_PORT} -sTCP:LISTEN || true)"
if [ -n "${PID}" ]; then
  echo "[dev_web] Killing PID(s): ${PID}"
  kill -15 ${PID} || true
  sleep 1
  kill -9 ${PID} || true
fi

export EXPO_PUBLIC_DEMO_MODE="${EXPO_PUBLIC_DEMO_MODE:-live}"
export EXPO_PUBLIC_BFF_BASE_URL="${EXPO_PUBLIC_BFF_BASE_URL:-http://localhost:8081}"

cd packages/app-expo
rm -rf .expo .expo-shared

echo "[dev_web] Starting Expo Web on :${WEB_PORT} (BFF=${EXPO_PUBLIC_BFF_BASE_URL})"
npx expo start --web -c --port ${WEB_PORT}
