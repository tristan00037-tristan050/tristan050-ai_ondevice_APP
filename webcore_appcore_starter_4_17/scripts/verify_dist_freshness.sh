#!/usr/bin/env bash
set -euo pipefail

# ✅ S6-S7: dist freshness gate (2중 앵커: healthz buildSha + src/dist timestamp)
# FAIL 조건:
# - 앵커 1: healthz의 buildSha가 git rev-parse HEAD와 불일치 → FAIL
# - 앵커 2: dist가 src보다 오래됨 → FAIL

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

source "./scripts/_lib/http_gate.sh" || {
  echo "[FAIL] http_gate.sh not found"
  exit 1
}

BFF="${BFF:-http://127.0.0.1:8081}"
HEALTHZ="$BFF/healthz"
PKG="$ROOT/packages/bff-accounting"
DIST="$PKG/dist/index.js"

FAILURES=()

echo "[verify] Dist Freshness Gate (2 anchors)"

# 앵커 1: healthz buildSha vs git HEAD
echo "[check] Anchor 1: healthz buildSha vs git HEAD"

TMP_BODY="$(mktemp -t dist_fresh_body.XXXXXX)"
TMP_HDR="$(mktemp -t dist_fresh_hdr.XXXXXX)"

code="$(http_gate_request "GET" "$HEALTHZ" "$TMP_BODY" "$TMP_HDR")"

if [ "$code" != "200" ]; then
  FAILURES+=("healthz returned $code (expected 200)")
else
  # JSON에서 buildSha 추출
  build_sha_json=$(jq -r '.buildSha // empty' "$TMP_BODY" 2>/dev/null || echo "")
  
  # 헤더에서 buildSha 추출 (X-OS-Build-SHA 또는 X-Build-SHA)
  build_sha_header=$(grep -i "^x-os-build-sha:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' || grep -i "^x-build-sha:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' || echo "")
  
  # JSON 또는 헤더 중 하나라도 있으면 사용
  build_sha="${build_sha_json:-${build_sha_header}}"
  
  if [ -z "$build_sha" ] || [ "$build_sha" = "unknown" ]; then
    FAILURES+=("healthz buildSha missing or unknown")
  else
    # git HEAD SHA
    git_head=$(git rev-parse HEAD 2>/dev/null || echo "")
    
    if [ -z "$git_head" ]; then
      FAILURES+=("git rev-parse HEAD failed")
    elif [ "$build_sha" != "$git_head" ]; then
      FAILURES+=("buildSha mismatch: healthz=$build_sha, git HEAD=$git_head")
    else
      echo "[OK] buildSha matches git HEAD ($build_sha)"
    fi
  fi
  
  # buildTime 형식 확인 (선택)
  build_time_json=$(jq -r '.buildTime // empty' "$TMP_BODY" 2>/dev/null || echo "")
  build_time_header=$(grep -i "^x-os-build-time:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' || echo "")
  build_time="${build_time_json:-${build_time_header}}"
  
  if [ -z "$build_time" ]; then
    FAILURES+=("healthz buildTime missing")
  else
    # ISO 8601 형식인지 간단 체크
    if ! echo "$build_time" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'; then
      FAILURES+=("buildTime format invalid: $build_time")
    else
      echo "[OK] buildTime format valid"
    fi
  fi
fi

rm -f "$TMP_BODY" "$TMP_HDR"

# 앵커 2: src vs dist timestamp
echo "[check] Anchor 2: src vs dist timestamp"

if [ ! -f "$DIST" ]; then
  FAILURES+=("dist missing: $DIST")
else
  # ✅ S6-S7: mtime 계산은 python으로 통일 (mac/linux 환경차 제거)
  PYTHON_MTIME="$ROOT/scripts/_lib/mtime_python.py"
  
  if [ ! -f "$PYTHON_MTIME" ]; then
    FAILURES+=("mtime_python.py not found: $PYTHON_MTIME")
  else
    # dist 최신 mtime (패키지 단위)
    dist_result=$(python3 "$PYTHON_MTIME" "$PKG/dist" "*.js" "*.map" 2>/dev/null || echo '{"latest_mtime":0}')
    dist_mtime=$(echo "$dist_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
    
    # src 최신 mtime (패키지 단위, 스캔 범위 고정)
    src_result=$(python3 "$PYTHON_MTIME" "$PKG/src" "*.ts" "*.tsx" "*.js" 2>/dev/null || echo '{"latest_mtime":0}')
    src_latest_mtime=$(echo "$src_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
    
    # config 파일 mtime도 체크
    for config_file in "$PKG/tsconfig.json" "$PKG/tsconfig.build.json" "$PKG/package.json"; do
      if [ -f "$config_file" ]; then
        config_result=$(python3 "$PYTHON_MTIME" "$(dirname "$config_file")" "$(basename "$config_file")" 2>/dev/null || echo '{"latest_mtime":0}')
        config_mtime=$(echo "$config_result" | jq -r '.latest_mtime // 0' 2>/dev/null || echo "0")
        if [ "$config_mtime" -gt "$src_latest_mtime" ]; then
          src_latest_mtime="$config_mtime"
        fi
      fi
    done
    
    if [ "$src_latest_mtime" -gt "$dist_mtime" ]; then
      FAILURES+=("dist is older than src: dist_mtime=$dist_mtime, src_latest_mtime=$src_latest_mtime")
    else
      echo "[OK] dist is fresh (dist_mtime >= src_latest_mtime)"
    fi
  fi
fi

# 결과 판정
if [ ${#FAILURES[@]} -gt 0 ]; then
  echo "[FAIL] Dist Freshness Gate"
  for failure in "${FAILURES[@]}"; do
    echo "  - $failure"
  done
  exit 1
else
  echo "[PASS] Dist Freshness Gate"
  exit 0
fi

