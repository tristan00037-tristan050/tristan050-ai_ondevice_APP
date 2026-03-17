#!/usr/bin/env bash
# =============================================================================
# setup.sh — AI-16 Phase B 학습 환경 세팅
# 네이버클라우드 GPU 서버에서 딱 한 번만 실행하면 됩니다.
# =============================================================================
set -euo pipefail

echo "=============================================="
echo " AI-16 Phase B 환경 세팅을 시작합니다!"
echo "=============================================="
echo ""

# ── 0. 현재 디렉토리 확인 ──────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
echo "[0/5] 레포지토리 루트: $REPO_ROOT"

# ── 1. CUDA 확인 ──────────────────────────────────────
echo ""
echo "[1/5] CUDA / GPU 확인 중..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version \
        --format=csv,noheader 2>/dev/null | head -4 || true
    echo "  ✅ GPU 확인 완료"
else
    echo "  ⚠️  nvidia-smi 없음 — GPU 드라이버 미설치 또는 CPU 서버"
    echo "  GPU 서버인지 확인 후 드라이버를 먼저 설치해 주세요."
    exit 1
fi

# ── 2. Python 버전 확인 ───────────────────────────────
echo ""
echo "[2/5] Python 버전 확인 중..."
PYTHON_BIN=""
for py in python3.11 python3.10 python3 python; do
    if command -v "$py" &>/dev/null; then
        VER=$("$py" --version 2>&1)
        echo "  ✅ $VER ($py)"
        PYTHON_BIN="$py"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "  ❌ Python을 찾을 수 없습니다. Python 3.10 이상을 먼저 설치해 주세요."
    exit 1
fi

# ── 3. pip 최신화 ─────────────────────────────────────
echo ""
echo "[3/5] pip 업그레이드 중..."
"$PYTHON_BIN" -m pip install --upgrade pip --quiet
echo "  ✅ pip 최신화 완료"

# ── 4. requirements.lock 기준 패키지 설치 ─────────────
echo ""
echo "[4/5] AI-16 의존 패키지 설치 중 (requirements.lock 기준)..."
echo "  ※ 인터넷 속도에 따라 5~15분 걸릴 수 있습니다. 기다려 주세요!"
echo ""

# bitsandbytes는 CUDA 빌드가 필요해 별도 설치
"$PYTHON_BIN" -m pip install \
    "transformers>=4.40,<5" \
    "trl==0.9.6" \
    "peft==0.10.0" \
    "bitsandbytes>=0.43,<1" \
    "datasets>=2.18,<4" \
    "accelerate>=0.28,<2" \
    "jsonschema>=4.21,<5" \
    --quiet

echo "  ✅ 패키지 설치 완료"

# ── 5. 설치 확인 ──────────────────────────────────────
echo ""
echo "[5/5] 설치된 패키지 최종 확인..."

for pkg in transformers trl peft bitsandbytes datasets accelerate torch; do
    VER=$("$PYTHON_BIN" -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "미설치")
    if [ "$VER" = "미설치" ]; then
        echo "  ❌ $pkg — 설치 실패"

    else
        echo "  ✅ $pkg==$VER"
    fi
done

echo ""
echo "=============================================="
echo " 환경 세팅 완료! 🎉"
echo " 다음 단계: bash scripts/cloud/run_training.sh"
echo "=============================================="
