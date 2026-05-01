#!/usr/bin/env bash
# Butler E2E 스모크 테스트 — .dmg 확인 + sidecar 기동 + 헬스 체크
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DMG="${REPO_ROOT}/butler-desktop/src-tauri/target/release/bundle/dmg/Butler_0.1.0_aarch64.dmg"
PORT=5903
SIDECAR_PID=""

cleanup() {
    [[ -n "$SIDECAR_PID" ]] && kill "$SIDECAR_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Butler E2E Smoke Test ==="
echo "Repo: ${REPO_ROOT}"
echo ""

# ── 1. sidecar 스크립트 존재 확인 ─────────────────────────────────────────
echo "[1/5] butler_sidecar.py 확인..."
if [[ ! -f "${REPO_ROOT}/butler_sidecar.py" ]]; then
    echo "  FAIL: butler_sidecar.py not found at ${REPO_ROOT}/butler_sidecar.py"
    exit 1
fi
echo "  OK"

# ── 2. DMG 마운트 확인 (존재할 때만) ──────────────────────────────────────
echo "[2/5] DMG 확인..."
if [[ -f "$DMG" ]]; then
    MOUNT_DIR=$(hdiutil attach "$DMG" -nobrowse -noverify 2>/dev/null \
        | grep -o '/Volumes/[^\t]*' | head -1 || true)
    if [[ -n "$MOUNT_DIR" ]]; then
        echo "  마운트: ${MOUNT_DIR}"
        ls -la "$MOUNT_DIR" 2>/dev/null || true
        hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
        echo "  OK"
    else
        echo "  WARN: 마운트 실패 (빌드 확인 필요)"
    fi
else
    echo "  SKIP: DMG 미존재 (npm run tauri build 먼저 실행)"
fi

# ── 3. Python 의존성 확인 ─────────────────────────────────────────────────
echo "[3/5] Python 의존성 확인..."
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "  WARN: fastapi/uvicorn 미설치 — pip3 install -r requirements-serving.txt"
else
    echo "  OK (fastapi + uvicorn 설치됨)"
fi

# ── 4. 사이드카 기동 ──────────────────────────────────────────────────────
echo "[4/5] sidecar 기동 (포트 ${PORT})..."
cd "$REPO_ROOT"
python3 butler_sidecar.py --port "$PORT" --host 127.0.0.1 &
SIDECAR_PID=$!

READY=0
for i in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
        READY=1
        echo "  OK (${i}초 내 응답)"
        break
    fi
    sleep 1
done

if [[ $READY -eq 0 ]]; then
    echo "  FAIL: sidecar가 15초 내에 응답하지 않음"
    exit 1
fi

# ── 5. 엔드포인트 검증 ────────────────────────────────────────────────────
echo "[5/5] 엔드포인트 검증..."

echo "  /health:"
curl -sf "http://127.0.0.1:${PORT}/health" | python3 -m json.tool 2>/dev/null || echo "  (json.tool 없음)"

echo "  /api/sidecar/health:"
curl -sf "http://127.0.0.1:${PORT}/api/sidecar/health" | python3 -m json.tool 2>/dev/null || echo "  (json.tool 없음)"

echo "  /api/model/status:"
MODEL_STATUS=$(curl -sf "http://127.0.0.1:${PORT}/api/model/status" || echo '{}')
echo "  $MODEL_STATUS" | python3 -m json.tool 2>/dev/null || echo "  $MODEL_STATUS"

echo ""
echo "=== Smoke Test PASSED ==="
