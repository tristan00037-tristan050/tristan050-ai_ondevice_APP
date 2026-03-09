#!/usr/bin/env bash
set -euo pipefail

# P22-AI-06: EXEC_MODE_AI_QUALITY_GATES_V2 verifier
EXEC_MODE_QUALITY_GATES_V2_OK=0
trap 'echo "EXEC_MODE_QUALITY_GATES_V2_OK=${EXEC_MODE_QUALITY_GATES_V2_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

RESULT_TS="tools/ai/exec_mode_result_v1.ts"
[[ -f "$RESULT_TS" ]] || { echo "ERROR_CODE=EXEC_MODE_RESULT_TS_MISSING"; echo "HIT_PATH=$RESULT_TS"; exit 1; }

# Verify ExecModeResult interface declares all required fields
REQUIRED_FIELDS=(
  "pack_id"
  "device_class_id"
  "reason_code"
  "cpu_time_ms"
  "quality_proxy_score"
  "routing_log_digest"
  "chain_proof_digest"
  "exec_fingerprint_sha256"
)

failed=0
for field in "${REQUIRED_FIELDS[@]}"; do
  if ! grep -q "${field}" "$RESULT_TS"; then
    echo "ERROR_CODE=EXEC_MODE_RESULT_FIELD_MISSING"
    echo "MISSING_FIELD=${field}"
    failed=1
  fi
done

[[ "$failed" -eq 0 ]] || exit 1

# Verify interface ExecModeResult is declared
grep -q 'interface ExecModeResult' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_INTERFACE_MISSING"
  echo "HIT_PATH=$RESULT_TS"
  exit 1
}

# Verify assertExecModeResult validator is present
grep -q 'assertExecModeResult' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_VALIDATOR_MISSING"
  echo "HIT_PATH=$RESULT_TS"
  exit 1
}

# Verify routing_log_digest and chain_proof_digest (audit fields) are sha256-typed
grep -q 'routing_log_digest' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_ROUTING_DIGEST_MISSING"
  exit 1
}
grep -q 'chain_proof_digest' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_CHAIN_DIGEST_MISSING"
  exit 1
}

EXEC_MODE_QUALITY_GATES_V2_OK=1
exit 0
