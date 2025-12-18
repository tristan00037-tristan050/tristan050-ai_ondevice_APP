#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/_ports.sh"

WEB_PORT=8083

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

echo "[dev_web] Freeing port ${WEB_PORT}..."
free_port_strict "${WEB_PORT}"

# 환경변수 강제 고정(혼선 재발 방지)
export EXPO_PUBLIC_BFF_BASE_URL="${EXPO_PUBLIC_BFF_BASE_URL:-http://127.0.0.1:8081}"
export EXPO_PUBLIC_DEMO_MODE="${EXPO_PUBLIC_DEMO_MODE:-live}"
export EXPO_PUBLIC_ENGINE_MODE="${EXPO_PUBLIC_ENGINE_MODE:-local-llm}"
export EXPO_PUBLIC_QA_TRIGGER_LLM_USAGE="${EXPO_PUBLIC_QA_TRIGGER_LLM_USAGE:-1}"

cd packages/app-expo

echo "[dev_web] Cleaning expo cache..."
rm -rf .expo .expo-shared

echo "[dev_web] Starting Expo Web on :${WEB_PORT}"
echo "[dev_web] DEMO_MODE=${EXPO_PUBLIC_DEMO_MODE} ENGINE_MODE=${EXPO_PUBLIC_ENGINE_MODE} QA_TRIGGER=${EXPO_PUBLIC_QA_TRIGGER_LLM_USAGE}"
echo "[dev_web] BFF=${EXPO_PUBLIC_BFF_BASE_URL}"

npx expo start --web -c --port "${WEB_PORT}"
