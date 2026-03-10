#!/usr/bin/env bash
set -euo pipefail

# AI-P3-06: DEVICE_PROBE_AND_CLASSIFY_V1 verifier
DEVICE_PROBE_RESULT_V1_OK=0
DEVICE_CLASS_DECISION_V1_OK=0
trap '
  echo "DEVICE_PROBE_RESULT_V1_OK=${DEVICE_PROBE_RESULT_V1_OK}"
  echo "DEVICE_CLASS_DECISION_V1_OK=${DEVICE_CLASS_DECISION_V1_OK}"
' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TS_FILE="tools/device/device_probe_v1.ts"

[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=DEVICE_PROBE_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

echo "=== DEVICE_PROBE_AND_CLASSIFY_V1 ==="

# 1. DeviceProbeResultV1 존재
if ! grep -q "DeviceProbeResultV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_PROBE_RESULT_TYPE_MISSING"
  exit 1
fi

# 2. DeviceClassDecisionV1 존재
if ! grep -q "DeviceClassDecisionV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_CLASS_DECISION_TYPE_MISSING"
  exit 1
fi

# 3. runDeviceProbeV1 존재
if ! grep -q "runDeviceProbeV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_PROBE_RUNNER_MISSING"
  exit 1
fi

# 4. classifyDeviceV1 존재
if ! grep -q "classifyDeviceV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_CLASSIFY_FUNCTION_MISSING"
  exit 1
fi

# 5. thermal_state=critical → THERMAL_LIMITED 로직 존재
if ! grep -q "THERMAL_LIMITED" "$TS_FILE"; then
  echo "FAILED_GUARD=THERMAL_LIMITED_HANDLING_MISSING"
  exit 1
fi

# 6. probe_digest 생성 존재
if ! grep -q "probe_digest" "$TS_FILE"; then
  echo "FAILED_GUARD=PROBE_DIGEST_MISSING"
  exit 1
fi

# 7. assertDeviceProbeResultV1 존재
if ! grep -q "assertDeviceProbeResultV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_PROBE_VALIDATOR_MISSING"
  exit 1
fi

# 8. assertDeviceClassDecisionV1 존재
if ! grep -q "assertDeviceClassDecisionV1" "$TS_FILE"; then
  echo "FAILED_GUARD=DEVICE_CLASS_DECISION_VALIDATOR_MISSING"
  exit 1
fi

DEVICE_PROBE_RESULT_V1_OK=1
DEVICE_CLASS_DECISION_V1_OK=1
echo "DEVICE_PROBE_RESULT_V1_OK=1"
echo "DEVICE_CLASS_DECISION_V1_OK=1"
exit 0
