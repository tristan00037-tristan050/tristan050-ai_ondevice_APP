#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

LOG_DIR="$ROOT/docs/ops"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/r10-s4-range-206-proof-$STAMP.log"

echo "[range206] starting deterministic upstream + bff + verify..." | tee "$LOG"

# 1) deterministic upstream
./scripts/dev_model_upstream.sh restart 2>&1 | tee -a "$LOG"

# 2) BFF (upstream base fixed)
export WEBLLM_UPSTREAM_BASE_URL="${WEBLLM_UPSTREAM_BASE_URL:-http://127.0.0.1:9099/webllm/}"
./scripts/dev_bff.sh restart 2>&1 | tee -a "$LOG"

# 3) verify 206 (PASS required)
WEBLLM_TEST_MODEL_ID=local-llm-v1 \
WEBLLM_TEST_MODEL_FILE=manifest.json \
./scripts/verify_range_206.sh 2>&1 | tee -a "$LOG"

echo "$LOG" > "$LOG_DIR/r10-s4-range-206-proof.latest"
echo "[range206] PASS. proof log: $LOG" | tee -a "$LOG"
