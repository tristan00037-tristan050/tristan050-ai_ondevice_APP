#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/tristan050-ai_ondevice_APP}"
TRAIN_FILE="${TRAIN_FILE:-/data/processed/train.jsonl}"
EVAL_FILE="${EVAL_FILE:-/data/processed/validation.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-output/butler_model_small_v1}"

echo '================================================'
echo '  butler_model_small_v1 (Qwen3-4B) 학습 시작'
echo "  TRAIN : $TRAIN_FILE"
echo "  OUTPUT: $OUTPUT_DIR"
echo '================================================'

cd "$REPO_DIR" && source /root/butler-venv/bin/activate

echo '[1/4] Qwen3-4B 오버레이 적용 중...'
python3 scripts/cloud/apply_small_overlay_v1.py --repo-dir "$REPO_DIR"

echo '[2/4] 학습 준비 검증 중...'
python3 scripts/verify/verify_ai20_bundle_readiness_v1.py \
  --repo-dir "$REPO_DIR" \
  --train-file "$TRAIN_FILE" \
  --eval-file "$EVAL_FILE"

echo '[3/4] QLoRA 학습 실행 중...'
python3 scripts/ai/finetune_qlora_small_v1.py \
  --train-file "$TRAIN_FILE" \
  --eval-file "$EVAL_FILE" \
  --output-dir "$OUTPUT_DIR"

echo '[4/4] 학습 결과 검증 중...'
python3 scripts/verify/verify_ai20_server_postrun_v1.py \
  --mode training-only \
  --output-dir "$OUTPUT_DIR"

echo '================================================'
echo '  학습 완료! 다음: bash scripts/cloud/run_phase_c_small_v1.sh'
echo '================================================'
