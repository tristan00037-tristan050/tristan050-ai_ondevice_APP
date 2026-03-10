#!/usr/bin/env bash
# VERIFY_PACK_ARTIFACT_CONTRACT_V1
# 팩 아티팩트 계약 검증 — tools/ai/pack_artifact_contract_v1.ts 존재 + verifyPackArtifactsV1 확인
set -euo pipefail

PACK_ARTIFACT_CONTRACT_V1_OK=0
trap 'echo "PACK_ARTIFACT_CONTRACT_V1_OK=${PACK_ARTIFACT_CONTRACT_V1_OK}"' EXIT

CONTRACT_FILE="tools/ai/pack_artifact_contract_v1.ts"

if [ ! -f "$CONTRACT_FILE" ]; then
  echo "FAILED_GUARD=PACK_ARTIFACT_CONTRACT_FILE_MISSING"
  echo "EXPECTED=$CONTRACT_FILE"
  exit 1
fi

for fn in "verifyPackArtifactsV1" "assertPackArtifactsCompleteV1" "REQUIRED_ARTIFACTS"; do
  if ! grep -q "$fn" "$CONTRACT_FILE"; then
    echo "FAILED_GUARD=PACK_ARTIFACT_CONTRACT_SYMBOL_MISSING:$fn"
    exit 1
  fi
done

REQUIRED=("model.onnx" "tokenizer.json" "config.json" "chat_template.jinja" "runtime_manifest.json" "SHA256SUMS")
for artifact in "${REQUIRED[@]}"; do
  if ! grep -q "$artifact" "$CONTRACT_FILE"; then
    echo "FAILED_GUARD=REQUIRED_ARTIFACT_NOT_IN_CONTRACT:$artifact"
    exit 1
  fi
done

echo "PACK_ARTIFACT_CONTRACT_V1_PASS=1"
PACK_ARTIFACT_CONTRACT_V1_OK=1
exit 0
