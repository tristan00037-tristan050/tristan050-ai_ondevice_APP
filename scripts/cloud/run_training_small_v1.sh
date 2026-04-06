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

# ── 캐시 복원 절차 ──────────────────────────────────────────
# butler-data 스토리지가 /data 에 마운트된 상태에서 실행할 것
# 새 서버에서 캐시 복원이 필요한 경우 아래 명령으로 rsync:
#   rsync -avz --progress /data/토크나이징_v2/ /root/tokenize_cache/
# 캐시 경로: /data/토크나이징_v2 (butler-data 스토리지 직접 사용)
# ────────────────────────────────────────────────────────────

echo '[3/4] QLoRA 학습 실행 중...'
python3 scripts/ai/finetune_qlora_small_v1.py \
  --train-file "$TRAIN_FILE" \
  --eval-file "$EVAL_FILE" \
  --output-dir "$OUTPUT_DIR" \
  --tokenize-cache-dir /data/토크나이징_v2

echo '[4/4] 학습 결과 검증 중...'
python3 scripts/verify/verify_ai20_server_postrun_v1.py \
  --mode training-only \
  --output-dir "$OUTPUT_DIR"

echo '================================================'
echo '  학습 완료! 다음: bash scripts/cloud/run_phase_c_small_v1.sh'
echo '================================================'
