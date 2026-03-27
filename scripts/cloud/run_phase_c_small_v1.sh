#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/tristan050-ai_ondevice_APP}"
ADAPTER_DIR="${ADAPTER_DIR:-output/butler_model_small_v1}"
LATENCY_BUDGET="${LATENCY_BUDGET:-8000}"
RESULT_FILE="/root/phase_c_small_result.json"

echo '================================================'
echo '  butler_model_small_v1 (Qwen3-4B) Phase C 검증'
echo '================================================'

cd "$REPO_DIR" && source /root/butler-venv/bin/activate

CUBLAS_WORKSPACE_CONFIG=:4096:8 \
python3 scripts/ai/run_phase_c_verification_v1.py \
  --adapter-dir "$ADAPTER_DIR" \
  --eval-file data/phase_c/butler_eval_v1.jsonl \
  --schema-file schemas/tool_call_schema_v3.json \
  --device-preference cuda \
  --load-mode 4bit \
  --latency-budget-ms "$LATENCY_BUDGET" \
  --out "$RESULT_FILE"

python3 scripts/verify/verify_ai20_completion_evidence_v1.py \
  --result-file "$RESULT_FILE" \
  --output-dir "$ADAPTER_DIR"

echo '================================================'
echo '  Phase C 완료! SSD 저장 후 서버 반납하세요.'
echo '  SSD 저장 경로: /학습자료/output/butler_model_small_v1/'
echo '================================================'
