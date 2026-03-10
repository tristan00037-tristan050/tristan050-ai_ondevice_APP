#!/usr/bin/env bash
# VERIFY_NO_RAW_PRECHECK_V1
# NO_RAW_OUTPUT_POLICY_V1 사전 체크 — tools/safety/no_raw_output_policy_v1.ts 존재 확인
set -euo pipefail

NO_RAW_PRECHECK_OK=0
trap 'echo "NO_RAW_PRECHECK_OK=${NO_RAW_PRECHECK_OK}"' EXIT

POLICY_FILE="tools/safety/no_raw_output_policy_v1.ts"

if [ ! -f "$POLICY_FILE" ]; then
  echo "FAILED_GUARD=NO_RAW_POLICY_FILE_MISSING"
  echo "EXPECTED=$POLICY_FILE"
  exit 1
fi

for fn in "computeSha256Hex" "safeLogDigestOnly" "throwSafeError" "assertNoRawInString"; do
  if ! grep -q "$fn" "$POLICY_FILE"; then
    echo "FAILED_GUARD=NO_RAW_POLICY_FUNCTION_MISSING:$fn"
    exit 1
  fi
done

echo "NO_RAW_PRECHECK_PASS=1"
NO_RAW_PRECHECK_OK=1
exit 0
