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
# butler-data 스토리지를 /data 에 직접 마운트하여 사용 (rsync 불필요)
# 스토리지 마운트: mkdir -p /data && mount /dev/vdb /data
# 확인: du -sh /data/토크나이징_v2/ → 49G
# 캐시 경로: /data/토크나이징_v2 (butler-data 스토리지 직접 사용)
# ────────────────────────────────────────────────────────────

if [ ! -d "/data/토크나이징_v2" ]; then
  echo "ERROR: /data/토크나이징_v2 가 존재하지 않습니다."
  echo "ERROR: butler-data 스토리지(ID: 134279703)를 /data 에 마운트한 후 실행하세요."
  echo "ERROR: mkdir -p /data && mount /dev/vdb /data"
  exit 1
fi
echo "TOKENIZE_CACHE_MOUNT_OK=1"

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
