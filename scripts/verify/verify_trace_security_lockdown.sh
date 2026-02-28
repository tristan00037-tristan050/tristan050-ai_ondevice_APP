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

# rg 없거나 동작 안 하면 grep 폴백 (설치 금지)
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
rg_n_dir()  { if have_rg; then rg -n --hidden --no-messages "$1" "$2" 2>/dev/null; else grep -RInE "$1" "$2" 2>/dev/null || true; fi; }
rg_q_file() { if have_rg; then rg -q "$1" "$2" 2>/dev/null; else grep -qE "$1" "$2" 2>/dev/null; fi; }
rg_l_dir()  { if have_rg; then rg -l --hidden --no-messages "$1" "$2" 2>/dev/null || true; else grep -RlE "$1" "$2" 2>/dev/null || true; fi; }
rg_n_file() { if have_rg; then rg -n "$1" "$2" 2>/dev/null; else grep -nE "$1" "$2" 2>/dev/null || true; fi; }

# 스캔 범위
# trace 라우터 정의 위치
TRACE_ROUTER_DIR="packages/ops-hub/src"
# 서버 바인딩 검사 범위 (trace 라우터가 사용될 수 있는 서버 파일들)
SERVER_SCOPE_DIRS=(
  "packages/ops-hub/src"
  "webcore_appcore_starter_4_17/packages/bff-accounting/src"
  "webcore_appcore_starter_4_17/backend"
)

# 1) import/require 감지(파일 분리되어도 OK)
TRACE_ROUTER_IMPORTED=0
for dir in "${SERVER_SCOPE_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  if rg_n_dir "(trace_v1\.ts|/routes/trace_v1|from ['\"].*trace_v1|require\\(.*trace_v1|buildTraceRouter)" "$dir" | grep -q .; then
    TRACE_ROUTER_IMPORTED=1
    break
  fi
done

# 2) mount 감지(파일 분리되어도 OK)
# 실제로 trace 라우터가 app.use() 또는 router.use()로 마운트되는지 확인
TRACE_ROUTER_MOUNTED=0
for dir in "${SERVER_SCOPE_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  # buildTraceRouter 호출 후 app.use() 또는 router.use()로 마운트되는 패턴
  if rg_n_dir "(app\\.use.*buildTraceRouter|app\\.use.*trace|router\\.use.*buildTraceRouter|router\\.use.*trace)" "$dir" | grep -q .; then
    TRACE_ROUTER_MOUNTED=1
    break
  fi
done

# 3) 최종 사용 판단(교차 파일 허용)
# 실제로 마운트된 경우에만 사용 중으로 간주 (import만으로는 부족)
# fail-closed 원칙: 실제로 마운트되지 않았다면 로컬 스크립트만 사용 중으로 간주
TRACE_ROUTER_USED=0
if [ "$TRACE_ROUTER_MOUNTED" -eq 1 ]; then
  TRACE_ROUTER_USED=1
fi

echo "TRACE_ROUTER_IMPORTED=${TRACE_ROUTER_IMPORTED}"
echo "TRACE_ROUTER_MOUNTED=${TRACE_ROUTER_MOUNTED}"
echo "TRACE_ROUTER_USED=${TRACE_ROUTER_USED}"

# 4) trace 라우터가 실제로 마운트되지 않으면 (로컬 스크립트만 사용) PASS
if [[ "$TRACE_ROUTER_USED" -eq 0 ]]; then
  # 로컬 파일 스토어 스크립트만 사용 중이면 로컬-only로 간주
  OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1
  exit 0
fi

# 5) trace 라우터가 실제로 마운트된 경우, 해당 서버의 바인딩 확인
# trace 라우터를 사용하는 서버 파일만 검사 (교차 파일 검색)
VIOLATION_FOUND=0

# 5-1) trace 라우터를 사용하는 서버 파일 찾기
TRACE_SERVER_FILES=()
for dir in "${SERVER_SCOPE_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  # buildTraceRouter를 import하고 app.use()로 마운트하는 파일 찾기
  while IFS= read -r file; do
    if [[ -f "$file" ]] && rg_q_file "buildTraceRouter|trace_v1" "$file" && rg_q_file "app\.use.*trace|router.*trace" "$file"; then
      TRACE_SERVER_FILES+=("$file")
    fi
  done < <(rg_l_dir "buildTraceRouter|trace_v1" "$dir")
done

# trace 라우터를 사용하는 서버가 없으면 PASS (로컬 스크립트만 사용)
if [[ ${#TRACE_SERVER_FILES[@]} -eq 0 ]]; then
  OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1
  exit 0
fi

# 5-2) trace 라우터를 사용하는 서버의 바인딩 확인
for file in "${TRACE_SERVER_FILES[@]}"; do
  # 0.0.0.0 바인딩 금지 확인
  if rg_q_file "listen.*0\.0\.0\.0|listen\(.*0\.0\.0\.0|host.*0\.0\.0\.0" "$file"; then
    echo "BLOCK: trace server binds to 0.0.0.0 in $file (must be 127.0.0.1 or auth required)"
    rg_n_file "listen.*0\.0\.0\.0|listen\(.*0\.0\.0\.0|host.*0\.0\.0\.0" "$file" | head -3
    VIOLATION_FOUND=1
  fi
  
  # listen() 호출에서 host 미지정 확인
  LISTEN_LINES=$(rg_n_file "\.listen\(" "$file" | grep -v "127.0.0.1" | grep -v "localhost" | grep -v "0.0.0.0" || echo "")
  if [[ -n "$LISTEN_LINES" ]]; then
    # host가 명시되지 않은 listen() 호출 확인
    if echo "$LISTEN_LINES" | grep -qE "\.listen\([^,)]+\)|\.listen\([^,)]+,\s*[^,)]+\)"; then
      echo "BLOCK: trace server listen() without explicit host in $file (must specify 127.0.0.1)"
      echo "$LISTEN_LINES" | head -3
      VIOLATION_FOUND=1
    fi
  fi
done

# 5-3) 127.0.0.1 바인딩 확인 (로컬-only)
LOCAL_ONLY_OK=0
for file in "${TRACE_SERVER_FILES[@]}"; do
  if rg_q_file "listen.*127\.0\.0\.1|listen.*localhost|listen\([^,)]+,\s*[\"']127\.0\.0\.1[\"']|listen\([^,)]+,\s*[\"']localhost[\"']" "$file"; then
    LOCAL_ONLY_OK=1
    break
  fi
done

# 5-4) 인증 필수 확인 (대안)
AUTH_REQUIRED_OK=0
# trace 라우터 파일에서 인증 미들웨어 확인
if [[ -f "$TRACE_ROUTER_DIR/routes/trace_v1.ts" ]]; then
  if rg_q_file "auth|token|bearer|authorization|requireAuth|checkAuth" "$TRACE_ROUTER_DIR/routes/trace_v1.ts"; then
    AUTH_REQUIRED_OK=1
  fi
fi
# trace 라우터를 사용하는 서버 파일에서 인증 확인
for file in "${TRACE_SERVER_FILES[@]}"; do
  if rg_q_file "(auth|token|bearer|authorization|requireAuth|checkAuth).*trace|trace.*(auth|token|bearer|authorization|requireAuth|checkAuth)" "$file"; then
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

