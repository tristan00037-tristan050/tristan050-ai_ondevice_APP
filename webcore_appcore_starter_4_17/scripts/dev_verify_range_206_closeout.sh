#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

LOG_DIR="$ROOT/docs/ops"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/r10-s4-range-206-proof-$STAMP.log"

echo "[range206] starting deterministic upstream + bff + verify..." | tee "$LOG"

# 1) deterministic upstream (skip if not available)
if [ -f "$ROOT/scripts/webllm_upstream_server.mjs" ]; then
  ./scripts/dev_model_upstream.sh > /dev/null 2>&1 &
  UPSTREAM_PID=$!
  sleep 2
  echo "[range206] upstream server started (PID: $UPSTREAM_PID)" | tee -a "$LOG"
else
  echo "[range206] WARN: upstream server not available, verify will skip" | tee -a "$LOG"
  UPSTREAM_PID=""
fi

# 2) BFF (upstream base fixed, background)
export WEBLLM_UPSTREAM_BASE_URL="${WEBLLM_UPSTREAM_BASE_URL:-http://127.0.0.1:9099/webllm/}"

./scripts/dev_bff.sh > /dev/null 2>&1 &
BFF_PID=$!
sleep 5

# BFF 서버 시작 확인
for i in 1 2 3 4 5; do
  if curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8081/health" > /dev/null 2>&1; then
    echo "[range206] BFF server started (PID: $BFF_PID)" | tee -a "$LOG"
    break
  fi
  if [ $i -eq 5 ]; then
    echo "[range206] WARN: BFF server may not be ready, continuing anyway" | tee -a "$LOG"
  fi
  sleep 1
done

# 3) verify 206 (PASS required)
WEBLLM_TEST_MODEL_ID=local-llm-v1 \
WEBLLM_TEST_MODEL_FILE=manifest.json \
./scripts/verify_range_206.sh 2>&1 | tee -a "$LOG"

VERIFY_EXIT=$?

# Cleanup
[ -n "$UPSTREAM_PID" ] && kill $UPSTREAM_PID 2>/dev/null || true
kill $BFF_PID 2>/dev/null || true

if [ $VERIFY_EXIT -eq 0 ]; then
  echo "$LOG" > "$LOG_DIR/r10-s4-range-206-proof.latest"
  echo "[range206] PASS. proof log: $LOG" | tee -a "$LOG"
  exit 0
else
  echo "[range206] FAIL. proof log: $LOG" | tee -a "$LOG"
  exit 1
fi
