#!/usr/bin/env bash
set -euo pipefail

# P22-AI-06 / P23-P0B-04 / P23-P2B-04: EXEC_MODE_AI_QUALITY_GATES_V2 verifier (ExecModeResultV3 + V4)
EXEC_MODE_QUALITY_GATES_V2_OK=0
EXEC_MODE_V4_OK=0
trap 'echo "EXEC_MODE_QUALITY_GATES_V2_OK=${EXEC_MODE_QUALITY_GATES_V2_OK}"; echo "EXEC_MODE_V4_OK=${EXEC_MODE_V4_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

RESULT_TS="tools/ai/exec_mode_result_v1.ts"
[[ -f "$RESULT_TS" ]] || { echo "ERROR_CODE=EXEC_MODE_RESULT_TS_MISSING"; echo "HIT_PATH=$RESULT_TS"; exit 1; }

failed=0

# Verify ExecModeResultV3 interface is declared
grep -q 'interface ExecModeResultV3' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_V3_INTERFACE_MISSING"
  echo "HIT_PATH=$RESULT_TS"
  failed=1
}

# Verify required fields exist in file
REQUIRED_FIELDS=(
  "pack_id"
  "device_class_id"
  "reason_code"
  "routing_decision_digest"
  "routing_event_id"
  "chain_proof_digest"
  "pack_identity_digest"
  "exec_fingerprint_sha256"
  "observation"
)

for field in "${REQUIRED_FIELDS[@]}"; do
  if ! grep -q "${field}" "$RESULT_TS"; then
    echo "ERROR_CODE=EXEC_MODE_RESULT_FIELD_MISSING"
    echo "MISSING_FIELD=${field}"
    failed=1
  fi
done

# Verify ExecObservation interface is declared (bigint → string fields)
grep -q 'interface ExecObservation' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_OBSERVATION_INTERFACE_MISSING"
  failed=1
}

# Verify ExecIdentityMaterial interface is declared
grep -q 'interface ExecIdentityMaterial' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_IDENTITY_MATERIAL_INTERFACE_MISSING"
  failed=1
}

# Verify assertExecModeResultV3 validator is present
grep -q 'assertExecModeResultV3' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_RESULT_V3_VALIDATOR_MISSING"
  echo "HIT_PATH=$RESULT_TS"
  failed=1
}

# Verify buildPackIdentityDigest and buildExecFingerprintSha256 are present
grep -q 'buildPackIdentityDigest' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_PACK_IDENTITY_BUILDER_MISSING"
  failed=1
}
grep -q 'buildExecFingerprintSha256' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_EXEC_FINGERPRINT_BUILDER_MISSING"
  failed=1
}

# Verify typedDigest is imported (single source)
grep -q 'typedDigest' "$RESULT_TS" || {
  echo "ERROR_CODE=EXEC_MODE_TYPED_DIGEST_IMPORT_MISSING"
  failed=1
}

[[ "$failed" -eq 0 ]] || exit 1

EXEC_MODE_QUALITY_GATES_V2_OK=1

# V4 checks (P23-P2B-04)
V4_SYMBOLS=(
  "ExecModeResultV4"
  "assertExecModeResultV4"
  "KvCacheMode"
  "KvPolicy"
  "buildPackIdentityDigestV2"
  "EXEC_V4_MISSING_FIELD"
  "EXEC_V4_MISSING_PRINCIPAL_ID"
  "EXEC_V4_MISSING_ORG_ID"
  "EXEC_V4_KV_ACTIVE_WITHOUT_POLICY_PARAMS_DIGEST"
  "logical_pack_digest"
  "compiled_pack_digest"
  "tokenizer_template_digest"
  "principal_id"
  "org_id"
  "rollout_ring"
)
for sym in "${V4_SYMBOLS[@]}"; do
  if ! grep -q "$sym" "$RESULT_TS"; then
    echo "ERROR_CODE=EXEC_MODE_V4_SYMBOL_MISSING"
    echo "MISSING_SYMBOL=$sym"
    failed=1
  fi
done

[[ "$failed" -eq 0 ]] || exit 1

EXEC_MODE_V4_OK=1
exit 0
