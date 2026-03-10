#!/usr/bin/env bash
set -euo pipefail

# P25-ENT-H2: EXEC_MODE_V4_STRICT_VALIDATION_V1
EXEC_MODE_V4_STRICT_OK=0
trap 'echo "EXEC_MODE_V4_STRICT_OK=${EXEC_MODE_V4_STRICT_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TS_FILE="tools/ai/exec_mode_result_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=EXEC_MODE_RESULT_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

echo "=== EXEC_MODE_V4_STRICT_VALIDATION_V1 ==="

# 1. assertSha256Hex 존재 확인
if ! grep -q "assertSha256Hex" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V4_SHA256_HELPER_MISSING"
  exit 1
fi

# 2. assertExecModeResultV4Strict 존재 확인
if ! grep -q "assertExecModeResultV4Strict" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V4_STRICT_VALIDATOR_MISSING"
  exit 1
fi

# 3. rollout_ring 4개 값 검증 로직 존재 확인
if ! grep -q "ring0_canary" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V4_ROLLOUT_RING_CHECK_MISSING"
  exit 1
fi

# 4. routing_event_id != routing_decision_digest 체크 존재 확인
if ! grep -q "ROUTING_EVENT_ID_MUST_DIFFER" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V4_ROUTING_SEPARATION_CHECK_MISSING"
  exit 1
fi

# 5. kv_cache_mode active 체크 존재 확인
if ! grep -q "KV_ACTIVE_WITHOUT_POLICY_PARAMS_DIGEST" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V4_KV_ACTIVE_CHECK_MISSING"
  exit 1
fi

EXEC_MODE_V4_STRICT_OK=1
echo "EXEC_MODE_V4_STRICT_OK=1"
exit 0
