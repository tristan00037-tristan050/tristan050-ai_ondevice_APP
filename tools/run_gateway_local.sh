#!/usr/bin/env bash
set -euo pipefail

# Gateway 로컬 실행 스크립트 (원샷)
# 목적: npm workspaces 없이 bff-accounting을 직접 실행

echo "=== Gateway 로컬 실행 스크립트 ==="
echo ""

# 1) git 레포 루트 찾기
REPO_ROOT=""
if command -v git >/dev/null 2>&1; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
fi

if [[ -z "$REPO_ROOT" ]] || [[ ! -d "$REPO_ROOT" ]]; then
  echo "❌ 오류: git 레포 루트를 찾을 수 없습니다."
  echo "   현재 위치에서 git 레포 안에 있는지 확인해주세요."
  exit 1
fi

echo "✅ 레포 루트: $REPO_ROOT"
cd "$REPO_ROOT"

# 2) bff-accounting 디렉터리 확인
BFF_DIR="$REPO_ROOT/webcore_appcore_starter_4_17/packages/bff-accounting"
if [[ ! -d "$BFF_DIR" ]]; then
  echo "❌ 오류: bff-accounting 디렉터리를 찾을 수 없습니다."
  echo "   예상 위치: $BFF_DIR"
  echo "   레포 구조를 확인해주세요."
  exit 1
fi

echo "✅ bff-accounting 디렉터리 확인: $BFF_DIR"
cd "$BFF_DIR"

# 3) 포트 8081 점검 (시작 전)
PORT=8081
echo ""
echo "=== 포트 $PORT 점검 (시작 전) ==="

# LISTEN 상태인 프로세스 찾기
LISTEN_PIDS=$(lsof -nP -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || echo "")

if [[ -n "$LISTEN_PIDS" ]]; then
  echo "⚠️  포트 $PORT에 이미 실행 중인 프로세스가 있습니다:"
  for PID in $LISTEN_PIDS; do
    CMD=$(ps -p "$PID" -o command= 2>/dev/null || echo "unknown")
    echo "   PID: $PID"
    echo "   명령어: $CMD"
    
    # bff-accounting/node 프로세스만 종료 대상
    if echo "$CMD" | grep -qE "(bff-accounting|node.*dist/index.js)"; then
      echo "   → 이 프로세스를 종료합니다..."
      kill -15 "$PID" 2>/dev/null || true
      sleep 1
      kill -9 "$PID" 2>/dev/null || true
      echo "   ✅ 종료 완료"
    else
      echo "   ⚠️  다른 프로세스입니다. 수동으로 확인해주세요."
      echo "   종료 명령어: kill $PID"
      exit 1
    fi
  done
  sleep 1
else
  echo "✅ 포트 $PORT가 비어있습니다."
fi

# 4) npm install
echo ""
echo "=== npm install ==="
if [[ ! -d "node_modules" ]] || [[ ! -f "package-lock.json" ]]; then
  echo "node_modules가 없습니다. npm install을 실행합니다..."
  npm install
else
  echo "✅ node_modules 존재 확인"
fi

# 5) npm run build
echo ""
echo "=== npm run build ==="
npm run build

if [[ ! -f "dist/index.js" ]]; then
  echo "❌ 오류: 빌드 후 dist/index.js 파일이 없습니다."
  echo "   빌드 로그를 확인해주세요."
  exit 1
fi

echo "✅ 빌드 완료"

# 6) 서버 시작 (백그라운드)
echo ""
echo "=== Gateway 서버 시작 (포트 $PORT) ==="

# 로그 파일 준비
LOG_FILE="/tmp/gateway_local.log"
PID_FILE="/tmp/gateway_local.pid"

# 기존 로그 백업
if [[ -f "$LOG_FILE" ]]; then
  mv "$LOG_FILE" "${LOG_FILE}.old" 2>/dev/null || true
fi

# 환경 변수 설정
export PORT=$PORT
export USE_PG="${USE_PG:-1}"
export DATABASE_URL="${DATABASE_URL:-postgres://app:app@127.0.0.1:5432/app}"
export EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-dev-export-secret}"

# 서버 시작 (백그라운드)
echo "서버를 시작합니다..."
nohup npm start > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

echo "✅ 서버 시작됨 (PID: $SERVER_PID)"
echo "   로그 파일: $LOG_FILE"

# 7) healthz 폴링 (최대 30초)
echo ""
echo "=== 서버 준비 대기 중... ==="
HEALTHZ_URL="http://127.0.0.1:${PORT}/healthz"
MAX_WAIT=30
READY=false

for i in $(seq 1 $MAX_WAIT); do
  HTTP_CODE=$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 2 "$HEALTHZ_URL" 2>/dev/null || echo "000")
  
  if [[ "$HTTP_CODE" == "200" ]]; then
    READY=true
    echo "✅ 서버 준비 완료! (${i}초 후)"
    
    # buildSha 출력
    BUILD_SHA=$(curl -fsS "$HEALTHZ_URL" 2>/dev/null | head -c 40 || echo "")
    if [[ -n "$BUILD_SHA" ]]; then
      echo "   buildSha: ${BUILD_SHA}..."
    fi
    
    break
  fi
  
  if [[ $((i % 5)) -eq 0 ]]; then
    echo "   대기 중... (${i}/${MAX_WAIT}초, HTTP $HTTP_CODE)"
  fi
  
  sleep 1
done

if [[ "$READY" != "true" ]]; then
  echo ""
  echo "❌ 서버가 준비되지 않았습니다 (${MAX_WAIT}초 초과)"
  echo ""
  echo "서버 로그 확인 위치:"
  echo "   tail -f $LOG_FILE"
  echo ""
  echo "서버 프로세스 확인:"
  echo "   ps -p $SERVER_PID"
  echo ""
  echo "서버 종료:"
  echo "   kill $SERVER_PID"
  echo ""
  echo "마지막 로그 (20줄):"
  tail -n 20 "$LOG_FILE" 2>/dev/null || echo "(로그 파일 없음)"
  exit 1
fi

echo ""
echo "=== Gateway 서버 실행 완료 ==="
echo "   URL: http://127.0.0.1:${PORT}"
echo "   Healthz: http://127.0.0.1:${PORT}/healthz"
echo "   PID: $SERVER_PID"
echo "   로그: $LOG_FILE"
echo ""
echo "서버를 종료하려면:"
echo "   kill $SERVER_PID"
echo "   또는: kill \$(cat $PID_FILE)"
echo ""

