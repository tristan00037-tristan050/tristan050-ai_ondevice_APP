#!/usr/bin/env bash
set -euo pipefail

# A-3.1: Trace Security Lockdown
# 목표: trace 경로는 "로컬-only" 또는 "인증 필수" 중 하나로 고정, 0.0.0.0 노출 경로 0

OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=0

cleanup() {
  echo "OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=${OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK}"
  if [[ "${OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v rg >/dev/null 2>&1 || { echo "BLOCK: ripgrep (rg) not found"; exit 1; }

# 1) trace 관련 HTTP 서버/엔드포인트 파일 찾기
TRACE_ROUTE_FILES=(
  "packages/ops-hub/src/routes/trace_v1.ts"
)

TRACE_SERVER_FILES=(
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/index.ts"
  "webcore_appcore_starter_4_17/backend/telemetry/index.ts"
  "webcore_appcore_starter_4_17/backend/control_plane/index.ts"
)

# 2) trace 라우터가 실제로 사용되는지 확인 (import/require 체크)
TRACE_ROUTER_USED=0
for file in "${TRACE_SERVER_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    continue
  fi
  
  # buildTraceRouter 또는 trace_v1 import/require 확인
  if rg -q "buildTraceRouter|from.*trace_v1|require.*trace_v1|trace.*router" "$file" 2>/dev/null; then
    # 실제로 app.use() 또는 router 사용 확인
    if rg -q "app\.use.*trace|router.*trace|/v1/trace" "$file" 2>/dev/null; then
      TRACE_ROUTER_USED=1
      break
    fi
  fi
done

# 3) trace 라우터가 사용되지 않으면 (로컬 스크립트만 사용) PASS
if [[ "$TRACE_ROUTER_USED" -eq 0 ]]; then
  # 로컬 파일 스토어 스크립트만 사용 중이면 로컬-only로 간주
  OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1
  exit 0
fi

# 4) trace 라우터가 사용되는 경우, 서버 바인딩 확인
VIOLATION_FOUND=0

# 4-1) 0.0.0.0 바인딩 금지 확인
for file in "${TRACE_SERVER_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    continue
  fi
  
  # trace 라우터를 사용하는지 확인
  if ! rg -q "buildTraceRouter|trace.*router|trace_v1" "$file" 2>/dev/null; then
    continue
  fi
  
  # 0.0.0.0 바인딩 확인
  if rg -q "listen.*0\.0\.0\.0|listen\(.*0\.0\.0\.0|host.*0\.0\.0\.0" "$file" 2>/dev/null; then
    echo "BLOCK: trace server binds to 0.0.0.0 in $file (must be 127.0.0.1 or auth required)"
    rg -n "listen.*0\.0\.0\.0|listen\(.*0\.0\.0\.0|host.*0\.0\.0\.0" "$file" | head -3
    VIOLATION_FOUND=1
  fi
  
  # listen() 호출에서 host 미지정 또는 0.0.0.0 확인
  if rg -q "\.listen\([^,)]+\)" "$file" 2>/dev/null; then
    # listen(PORT) 또는 listen(PORT, callback) 형태 (host 미지정)
    LISTEN_LINES=$(rg -n "\.listen\(" "$file" | grep -v "127.0.0.1" | grep -v "localhost" || echo "")
    if [[ -n "$LISTEN_LINES" ]]; then
      # host가 명시되지 않은 경우 확인
      for line in "$LISTEN_LINES"; do
        if echo "$line" | rg -q "\.listen\([^,)]+\)"; then
          echo "BLOCK: trace server listen() without explicit host in $file (must specify 127.0.0.1)"
          echo "$line"
          VIOLATION_FOUND=1
        fi
      done
    fi
  fi
done

# 4-2) 127.0.0.1 바인딩 확인 (로컬-only)
LOCAL_ONLY_OK=0
for file in "${TRACE_SERVER_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    continue
  fi
  
  if ! rg -q "buildTraceRouter|trace.*router|trace_v1" "$file" 2>/dev/null; then
    continue
  fi
  
  # 127.0.0.1 또는 localhost 바인딩 확인
  if rg -q "listen.*127\.0\.0\.1|listen.*localhost|listen\([^,)]+,\s*[\"']127\.0\.0\.1[\"']|listen\([^,)]+,\s*[\"']localhost[\"']" "$file" 2>/dev/null; then
    LOCAL_ONLY_OK=1
    break
  fi
done

# 4-3) 인증 필수 확인 (대안)
AUTH_REQUIRED_OK=0
for file in "${TRACE_ROUTE_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    continue
  fi
  
  # 인증 미들웨어 또는 헤더 체크 확인
  if rg -q "auth|token|bearer|authorization|requireAuth|checkAuth" "$file" 2>/dev/null; then
    AUTH_REQUIRED_OK=1
    break
  fi
done

# 5) 판정: 로컬-only 또는 인증 필수 중 하나 만족해야 함
if [[ "$VIOLATION_FOUND" -eq 1 ]]; then
  echo "BLOCK: trace endpoint violates security policy (0.0.0.0 binding or no host specified)"
  exit 1
fi

if [[ "$LOCAL_ONLY_OK" -eq 1 ]] || [[ "$AUTH_REQUIRED_OK" -eq 1 ]]; then
  OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1
  exit 0
fi

# 6) 둘 다 만족하지 않으면 FAIL
echo "BLOCK: trace endpoint must be local-only (127.0.0.1) or auth-required"
exit 1

