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

# --- BEGIN: dist freshness guard (S6-S7 hardening) ---
# ✅ 하드 룰: dist freshness 체크 + 빌드가 완료된 후에만 BFF 시작
# ✅ DEV_BFF_SKIP_BUILD=1이면 dist freshness 체크 및 build 완전 스킵
if [ "${DEV_BFF_SKIP_BUILD:-0}" = "1" ]; then
  echo "[dev_bff] SKIP_BUILD=1 -> skip dist freshness + build"
else
  ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
  PKG="$ROOT/packages/bff-accounting"
  DIST="$PKG/dist/index.js"

  # 1) Anchor 2만 먼저 체크 (src vs dist timestamp, BFF 시작 전 가능)
  echo "[dev_bff] Checking dist freshness (src vs dist timestamp)..."
  PYTHON_MTIME="$ROOT/scripts/_lib/mtime_python.py"

  if [ -f "$DIST" ] && [ -f "$PYTHON_MTIME" ]; then
    dist_result=$(python3 "$PYTHON_MTIME" "$PKG/dist" "*.js" "*.map" 2>/dev/null || echo '{"latest_mtime":0}')
    dist_mtime=$(echo "$dist_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
    
    src_result=$(python3 "$PYTHON_MTIME" "$PKG/src" "*.ts" "*.tsx" "*.js" 2>/dev/null || echo '{"latest_mtime":0}')
    src_latest_mtime=$(echo "$src_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
    
    for config_file in "$PKG/tsconfig.json" "$PKG/package.json"; do
      if [ -f "$config_file" ]; then
        config_result=$(python3 "$PYTHON_MTIME" "$(dirname "$config_file")" "$(basename "$config_file")" 2>/dev/null || echo '{"latest_mtime":0}')
        config_mtime=$(echo "$config_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
        if [ "$config_mtime" -gt "$src_latest_mtime" ]; then
          src_latest_mtime="$config_mtime"
        fi
      fi
    done
    
    if [ "$src_latest_mtime" -gt "$dist_mtime" ]; then
      echo "[dev_bff] dist is older than src -> build required"
      NEED_BUILD=1
    else
      echo "[dev_bff] dist is fresh (skip build)"
      NEED_BUILD=0
    fi
  else
    echo "[dev_bff] dist missing or mtime_python.py not found -> build required"
    NEED_BUILD=1
  fi

  # 2) 빌드 필요 시 수행
  # ✅ C) workspace 빌드 표준 1개로 통일
  if [ "$NEED_BUILD" = "1" ]; then
    echo "[dev_bff] Building @appcore/bff-accounting..."
    npm run build --workspace=@appcore/bff-accounting || {
      echo "[dev_bff] FAIL: build failed"
      exit 1
    }
  fi
fi

# 3) Anchor 1 (healthz buildSha)는 BFF 시작 후에 체크 (아래 healthz 폴링에서 수행)
# --- END: dist freshness guard ---

echo "[dev_bff] Starting BFF on :${PORT}"
echo "[dev_bff] DATABASE_URL=${DATABASE_URL}"
echo "[dev_bff] WEBLLM_UPSTREAM_BASE_URL=${WEBLLM_UPSTREAM_BASE_URL}"

# BFF를 백그라운드로 시작
echo "[dev_bff] Starting BFF in background..."
npm run dev:bff > /tmp/bff_dev.log 2>&1 &
BFF_PID=$!

# healthz 폴링 (상한 50초, curl --max-time 사용)
echo "[dev_bff] Waiting for BFF to be ready..."
HEALTHZ="http://127.0.0.1:${PORT}/healthz"
BFF_READY=false
MAX_WAIT=50

for i in $(seq 1 $MAX_WAIT); do
  sleep 1
  if curl -fsS --max-time 2 "$HEALTHZ" >/dev/null 2>&1; then
    BFF_READY=true
    echo "[dev_bff] BFF ready after ${i}s"
    break
  fi
  if [ $((i % 5)) -eq 0 ]; then
    echo "[dev_bff] Waiting... (${i}/${MAX_WAIT}s)"
  fi
done

if [ "$BFF_READY" != "true" ]; then
  echo "[dev_bff] FAIL: BFF did not become ready within ${MAX_WAIT}s"
  echo "[dev_bff] BFF log (last 30 lines):"
  tail -n 30 /tmp/bff_dev.log 2>/dev/null || echo "(log not available)"
  kill $BFF_PID 2>/dev/null || true
  exit 1
fi

# ✅ Anchor 1: healthz buildSha vs git HEAD 체크 (BFF 시작 후)
# ⚠️ 하드 룰: buildSha가 unknown/빈값/40자 미만/비-hex이면 즉시 FAIL (exit 1)
# ✅ D) 헤더/바디 완전 분리 + fail-fast + PASS 요약 단일화
echo "[dev_bff] Verifying build anchor (healthz buildSha vs git HEAD)..."
TMP_HDR="$(mktemp -t bff_healthz_hdr.XXXXXX)"
TMP_BODY="$(mktemp -t bff_healthz_body.XXXXXX)"

# 헤더는 반드시: curl -fsSI (헤더만)
code_hdr=$(curl -fsSI --max-time 3 "$HEALTHZ" -D "$TMP_HDR" -o /dev/null 2>/dev/null && echo "200" || echo "000")

if [ "$code_hdr" != "200" ]; then
  echo "[dev_bff] FAIL: healthz header request returned $code_hdr (expected 200)"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# 바디는 반드시: curl -fsS (바디만, 헤더와 분리)
code_body=$(curl -fsS --max-time 3 "$HEALTHZ" -o "$TMP_BODY" 2>/dev/null && echo "200" || echo "000")

if [ "$code_body" != "200" ]; then
  echo "[dev_bff] FAIL: healthz body request returned $code_body (expected 200)"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# 헤더 buildSha 추출 (완전 분리)
build_sha_header=$(grep -i "^x-os-build-sha:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' | head -1 || echo "")

# JSON buildSha 추출 (완전 분리)
build_sha_json=$(jq -r '.buildSha // empty' "$TMP_BODY" 2>/dev/null || echo "")

# 하드 FAIL: JSON/헤더 중 하나라도 누락 시 즉시 FAIL
if [ -z "$build_sha_json" ] && [ -z "$build_sha_header" ]; then
  echo "[dev_bff] FAIL: healthz buildSha missing in both JSON and header"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

# 하드 FAIL: 헤더 SHA == JSON SHA 강제
if [ -n "$build_sha_json" ] && [ -n "$build_sha_header" ] && [ "$build_sha_json" != "$build_sha_header" ]; then
  echo "[dev_bff] FAIL: buildSha mismatch: header=$build_sha_header, json=$build_sha_json"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

build_sha="${build_sha_json:-${build_sha_header}}"

# 하드 FAIL: empty/unknown 체크
if [ -z "$build_sha" ] || [ "$build_sha" = "unknown" ]; then
  echo "[dev_bff] FAIL: healthz buildSha is unknown (build_info missing/invalid)"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

# 하드 FAIL: 40자 미만 체크
if [ ${#build_sha} -lt 40 ]; then
  echo "[dev_bff] FAIL: healthz buildSha length is ${#build_sha} (expected 40): $build_sha"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

# 하드 FAIL: 정규식 40-hex 검증
if ! echo "$build_sha" | grep -qE '^[0-9a-f]{40}$'; then
  echo "[dev_bff] FAIL: healthz buildSha is not 40-hex: $build_sha"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

git_head=$(git rev-parse HEAD 2>/dev/null || echo "")

if [ -z "$git_head" ]; then
  echo "[dev_bff] FAIL: git rev-parse HEAD failed"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

# 하드 FAIL: HEAD 일치 확인 (dev 환경 기준)
if [ "$build_sha" != "$git_head" ]; then
  echo "[dev_bff] FAIL: buildSha mismatch: healthz=$build_sha, git HEAD=$git_head"
  rm -f "$TMP_BODY" "$TMP_HDR"
  exit 1
fi

# ✅ 모든 체크 통과 후 PASS 요약 1회만 출력
git_head_short=$(echo "$git_head" | cut -c1-7)
echo "[dev_bff] OK: buildSha matches HEAD($git_head_short)"

rm -f "$TMP_BODY" "$TMP_HDR"

echo "[dev_bff] BFF started successfully (PID: $BFF_PID)"
echo "[dev_bff] Log: /tmp/bff_dev.log"
wait $BFF_PID
