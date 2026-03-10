#!/usr/bin/env bash
set -euo pipefail

# AI-P3-05: EXEC_FINGERPRINT_CANONICAL_V1 verifier
EXEC_FINGERPRINT_CANONICAL_V1_OK=0
EXEC_MODE_V5_STRICT_OK=0
trap '
  echo "EXEC_FINGERPRINT_CANONICAL_V1_OK=${EXEC_FINGERPRINT_CANONICAL_V1_OK}"
  echo "EXEC_MODE_V5_STRICT_OK=${EXEC_MODE_V5_STRICT_OK}"
' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# ExecModeResultV4/V5 is defined in tools/ai/exec_mode_result_v1.ts
TS_FILE="tools/ai/exec_mode_result_v1.ts"

[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=EXEC_MODE_RESULT_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

echo "=== EXEC_FINGERPRINT_CANONICAL_V1 ==="

# 1. ExecFingerprintMaterialV1 존재
if ! grep -q "ExecFingerprintMaterialV1" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_FINGERPRINT_MATERIAL_MISSING"
  exit 1
fi

# 2. ExecModeResultV5 존재
if ! grep -q "ExecModeResultV5" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_MODE_V5_MISSING"
  exit 1
fi

# 3. assertExecModeResultV5Strict 존재
if ! grep -q "assertExecModeResultV5Strict" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V5_STRICT_VALIDATOR_MISSING"
  exit 1
fi

# 4. buildExecFingerprintV1 존재
if ! grep -q "buildExecFingerprintV1" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_FINGERPRINT_BUILDER_MISSING"
  exit 1
fi

# 5. timestamp가 ExecFingerprintMaterialV1 인터페이스 body에 포함되지 않음 확인
if grep -A 20 "ExecFingerprintMaterialV1" "$TS_FILE" | grep -q "timestamp"; then
  echo "FAILED_GUARD=EXEC_FINGERPRINT_TIMESTAMP_CONTAMINATION"
  exit 1
fi

# 6. routing_event_id ≠ routing_decision_digest 검증 로직 존재
if ! grep -q "MUST_DIFFER_FROM_DECISION_DIGEST" "$TS_FILE"; then
  echo "FAILED_GUARD=EXEC_V5_ROUTING_ID_DIFFER_CHECK_MISSING"
  exit 1
fi

EXEC_FINGERPRINT_CANONICAL_V1_OK=1
EXEC_MODE_V5_STRICT_OK=1
echo "EXEC_FINGERPRINT_CANONICAL_V1_OK=1"
echo "EXEC_MODE_V5_STRICT_OK=1"
exit 0
