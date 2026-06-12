#!/usr/bin/env bash
# Butler E2E 스모크 테스트 — .dmg 확인 + sidecar 기동 + 헬스 체크 (FastAPI 모드 포함)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DMG="${REPO_ROOT}/butler-desktop/src-tauri/target/release/bundle/dmg/Butler_0.1.0_aarch64.dmg"
APP_PATH="${BUTLER_APP_PATH:-/Applications/Butler.app}"
APP_SMOKE_REQUIRED="${BUTLER_REQUIRE_INSTALLED_APP_SMOKE:-0}"
APP_LOG="${HOME}/Library/Logs/Butler/sidecar-launch.log"
PORT=5903
SIDECAR_PID=""
TEMP_VENV=""
OPEN_APP_LAUNCHED=0

cleanup() {
    [[ -n "$SIDECAR_PID" ]] && kill "$SIDECAR_PID" 2>/dev/null || true
    if [[ "$OPEN_APP_LAUNCHED" -eq 1 ]]; then
        osascript -e 'tell application "Butler" to quit' >/dev/null 2>&1 || true
    fi
    hdiutil detach /tmp/Butler_smoke 2>/dev/null || true
    [[ -n "$TEMP_VENV" ]] && rm -rf "$TEMP_VENV" || true
}
trap cleanup EXIT

echo "=== Butler E2E Smoke Test (v3 — open 실행 + FastAPI 모드 포함) ==="
echo "Repo: ${REPO_ROOT}"
echo ""

# ── 1. sidecar 스크립트 존재 확인 ─────────────────────────────────────────
echo "[1/6] butler_sidecar.py 확인..."
[[ -f "${REPO_ROOT}/butler_sidecar.py" ]] || { echo "  FAIL: butler_sidecar.py not found"; exit 1; }
[[ -f "${REPO_ROOT}/butler_pc_core/inference/chunk_worker.py" ]] || { echo "  FAIL: chunk_worker.py not found"; exit 1; }
echo "  OK (sidecar + chunk_worker)"

# ── 2. DMG 마운트 확인 (존재할 때만) ──────────────────────────────────────
echo "[2/6] DMG 확인..."
if [[ -f "$DMG" ]]; then
    hdiutil attach "$DMG" -mountpoint /tmp/Butler_smoke -nobrowse -noverify 2>/dev/null && MOUNTED=1 || MOUNTED=0
    if [[ $MOUNTED -eq 1 ]]; then
        echo "  마운트: /tmp/Butler_smoke"
        ls -la /tmp/Butler_smoke 2>/dev/null || true
        # sidecar 번들 포함 확인
        BUNDLE_SIDECAR="/tmp/Butler_smoke/Butler.app/Contents/Resources/butler_sidecar.py"
        if [[ -f "$BUNDLE_SIDECAR" ]]; then
            echo "  OK (butler_sidecar.py 번들 포함)"
        else
            echo "  WARN: butler_sidecar.py 번들 미포함 (tauri.conf.json resources 확인 필요)"
        fi
        hdiutil detach /tmp/Butler_smoke -quiet 2>/dev/null || true
    else
        echo "  WARN: 마운트 실패 (빌드 확인 필요)"
    fi
else
    echo "  SKIP: DMG 미존재 (npm run tauri build 먼저 실행)"
fi

# ── 3. 설치된 .app GUI open smoke (존재할 때만) ───────────────────────────
echo "[3/7] 설치된 Butler.app codesign + open smoke..."
if [[ "$(uname -s)" != "Darwin" ]]; then
    if [[ "$APP_SMOKE_REQUIRED" == "1" ]]; then
        echo "  FAIL: installed app smoke는 macOS에서만 실행 가능"
        exit 1
    fi
    echo "  SKIP: macOS 아님"
elif [[ -d "$APP_PATH" ]]; then
    codesign --verify --deep --strict "$APP_PATH"
    echo "  codesign: OK"
    rm -f "$APP_LOG"
    open -n "$APP_PATH"
    OPEN_APP_LAUNCHED=1
    READY=0
    for i in $(seq 1 60); do
        if curl -sf "http://127.0.0.1:8765/health" > /dev/null 2>&1; then
            READY=1
            echo "  open health: OK (${i}초 내 응답)"
            break
        fi
        sleep 1
    done
    if [[ $READY -eq 0 ]]; then
        echo "  FAIL: open 실행 sidecar가 60초 내에 응답하지 않음"
        echo "  log: ${APP_LOG}"
        [[ -f "$APP_LOG" ]] && tail -80 "$APP_LOG" || true
        exit 1
    fi
    if [[ -f "$APP_LOG" ]]; then
        echo "  sidecar launch log: OK"
    else
        echo "  FAIL: sidecar launch log 미생성 (${APP_LOG})"
        exit 1
    fi
else
    if [[ "$APP_SMOKE_REQUIRED" == "1" ]]; then
        echo "  FAIL: ${APP_PATH} 없음"
        exit 1
    fi
    echo "  SKIP: ${APP_PATH} 없음"
fi

# ── 3. FastAPI 환경 준비 ──────────────────────────────────────────────────
echo "[4/7] FastAPI 환경 준비..."
if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "  OK (기존 환경 사용)"
    PYTHON_CMD="python3"
else
    echo "  venv 생성 + requirements 설치..."
    TEMP_VENV=$(mktemp -d)
    python3 -m venv "$TEMP_VENV"
    source "$TEMP_VENV/bin/activate"
    pip install -q -r "${REPO_ROOT}/requirements-serving.txt" 2>&1 | tail -3
    PYTHON_CMD="$TEMP_VENV/bin/python3"
    echo "  OK (venv 준비 완료)"
fi

# ── 4. FastAPI 모드 sidecar 기동 ──────────────────────────────────────────
echo "[5/7] sidecar 기동 (포트 ${PORT})..."
cd "$REPO_ROOT"
${PYTHON_CMD} butler_sidecar.py --port "$PORT" --host 127.0.0.1 &
SIDECAR_PID=$!

READY=0
for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
        READY=1
        echo "  OK (${i}초 내 응답)"
        break
    fi
    sleep 1
done

if [[ $READY -eq 0 ]]; then
    echo "  FAIL: sidecar가 20초 내에 응답하지 않음"
    exit 1
fi

# ── 5. FastAPI 엔드포인트 검증 ────────────────────────────────────────────
echo "[6/7] 엔드포인트 검증..."

# /health
HEALTH=$(curl -sf "http://127.0.0.1:${PORT}/health" || echo "")
if echo "$HEALTH" | grep -q '"status"'; then
    echo "  /health: OK — $HEALTH"
else
    echo "  FAIL: /health 응답 없음 (HEALTH='$HEALTH')"
    exit 1
fi

# /api/sidecar/health (FastAPI 전용)
SIDECAR_HEALTH=$(curl -sf "http://127.0.0.1:${PORT}/api/sidecar/health" || echo "")
if echo "$SIDECAR_HEALTH" | grep -q '"status"'; then
    echo "  /api/sidecar/health: OK — $SIDECAR_HEALTH"
else
    echo "  WARN: /api/sidecar/health 응답 없음 (stdlib fallback 가능성)"
fi

# /api/model/status (FastAPI 전용)
MODEL=$(curl -sf "http://127.0.0.1:${PORT}/api/model/status" || echo "")
if echo "$MODEL" | grep -q '"status"'; then
    echo "  /api/model/status: OK — $MODEL"
else
    echo "  WARN: /api/model/status 응답 없음 (stdlib fallback 가능성)"
fi

# /api/analyze/stream — SSE reachable 확인
echo "  /api/analyze/stream SSE 도달 확인..."
SSE_RESP=$(curl -s -m 3 -X POST "http://127.0.0.1:${PORT}/api/analyze/stream" \
    -F "query=ping" -F "card_mode=free" -F "file_count=0" -F "total_chunks=1" 2>&1 | head -3 || true)
if echo "$SSE_RESP" | grep -q "event:"; then
    echo "  /api/analyze/stream: OK (SSE 이벤트 수신)"
else
    echo "  /api/analyze/stream: $SSE_RESP"
fi

# ── 6. Python 회귀 테스트 (sidecar_lifecycle) ─────────────────────────────
echo "[7/7] 회귀 테스트 실행..."
cd "$REPO_ROOT"
RESULT=$(${PYTHON_CMD} -m pytest tests/test_sidecar_lifecycle.py -v --tb=short 2>&1 | tail -15)
echo "$RESULT"
if echo "$RESULT" | grep -q "passed"; then
    echo "  OK"
else
    echo "  WARN: 테스트 결과 확인 필요"
fi

echo ""
echo "=== E2E 스모크 PASS (open 실행 + FastAPI 모드 검증 포함) ==="
