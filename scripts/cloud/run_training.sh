#!/usr/bin/env bash
# =============================================================================
# run_training.sh — AI-16 Phase B QLoRA 학습 실행
# setup.sh 실행 후 이 파일을 실행하세요.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# ── Python 바이너리 자동 탐지 ─────────────────────────────────────────────
PYTHON_BIN=""
for py in python3.11 python3.10 python3 python; do
    if command -v "$py" &>/dev/null; then
        PYTHON_BIN="$py"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python을 찾을 수 없습니다."
    exit 1
fi

# ── 설정값 ──────────────────────────────────────────────────────────────────
MODEL_ID="Qwen/Qwen2.5-7B-Instruct"   # Hugging Face 모델 ID
TRAIN_FILE="data/synthetic_v40/train.jsonl"
EVAL_FILE="data/synthetic_v40/validation.jsonl"
OUTPUT_DIR="output/butler_model_v1"
LOG_FILE="output/training.log"

echo "=============================================="
echo " AI-16 Phase B QLoRA 학습 시작"
echo "=============================================="
echo " 모델    : $MODEL_ID"
echo " 학습데이터: $TRAIN_FILE"
echo " eval데이터: $EVAL_FILE"
echo " 출력폴더 : $OUTPUT_DIR"
echo " 로그파일 : $LOG_FILE"
echo "=============================================="
echo ""
echo " ⏱  학습은 GPU 성능에 따라 수 시간 걸릴 수 있습니다."
echo "    터미널을 닫지 마세요! (screen/tmux 사용 권장)"
echo ""

# ── 출력 폴더 생성 ───────────────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
mkdir -p "tmp"

# ── 학습 데이터 존재 확인 ────────────────────────────────────────────────────
if [ ! -f "$TRAIN_FILE" ]; then
    echo "❌ 학습 데이터 파일이 없습니다: $TRAIN_FILE"
    echo "   먼저 데이터를 생성해 주세요:"
    echo "   python3 scripts/ai/generate_synthetic_data_v1_final.py --count 200 --out-dir data/synthetic_v40"
    exit 1
fi

# ── eval 파일 유무에 따라 인자 분기 ─────────────────────────────────────────
EVAL_ARG=""
if [ -f "$EVAL_FILE" ]; then
    EVAL_ARG="--eval-file $EVAL_FILE"
    echo "  ✅ eval 파일 발견: $EVAL_FILE"
else
    echo "  ℹ️  eval 파일 없음 — eval 없이 학습합니다"
fi

# ── dry-run으로 설정 먼저 확인 ───────────────────────────────────────────────
echo ""
echo "[준비] 설정 사전 검증 (dry-run)..."
"$PYTHON_BIN" scripts/ai/finetune_qlora_v3_5.py \
    --model-id "$MODEL_ID" \
    --train-file "$TRAIN_FILE" \
    $EVAL_ARG \
    --output-dir "$OUTPUT_DIR" \
    --dry-run \
    2>&1 | tee tmp/dryrun_preflight.log

echo ""
echo "[시작] 실제 학습을 시작합니다..."
echo ""

# ── 실제 학습 실행 ───────────────────────────────────────────────────────────
"$PYTHON_BIN" scripts/ai/finetune_qlora_v3_5.py \
    --model-id "$MODEL_ID" \
    --train-file "$TRAIN_FILE" \
    $EVAL_ARG \
    --output-dir "$OUTPUT_DIR" \
    --num-train-epochs 3 \
    --save-steps 200 \
    --save-total-limit 3 \
    2>&1 | tee "$LOG_FILE"

# ── 완료 확인 ────────────────────────────────────────────────────────────────
echo ""
if [ -d "$OUTPUT_DIR" ] && [ "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]; then
    echo "=============================================="
    echo " 학습완료! 이제 파일을 다운로드하세요 🎉"
    echo "=============================================="
    echo ""
    echo " 저장된 파일 목록:"
    ls -lh "$OUTPUT_DIR" | head -20
    echo ""
    echo " 다음 단계: bash scripts/cloud/download_and_cleanup.sh"
    echo "=============================================="
else
    echo "❌ 학습 결과 파일이 없습니다. 로그를 확인하세요: $LOG_FILE"
    exit 1
fi
