#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"

grep -RInE "BASE_MODEL_NAME *=.*v4|BASE_MODEL_SHA256_FULL *=.*60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f|BUTLER_BOX3_BASE_MODEL_PATH.*v4" \
  butler_pc_core/cards/box3 \
  --exclude-dir=lora_fusion \
  --exclude='*test*' \
  --exclude='*fixture*' \
  --exclude='*.md' \
  && { echo "BLOCK_V4_DEFAULT_REFERENCE"; exit 1; } || echo "V4_DEFAULT_REFERENCE_ZERO=true"

grep -RInE "lora_path|lora_adapter|Llama\(.*lora" butler_pc_core/cards/box3/local_sealed_runner.py \
  && { echo "BLOCK_HELPER35_RUNTIME_STACK_REFERENCE"; exit 1; } || echo "HELPER35_RUNTIME_STACK_ZERO=true"

grep -RInE "grounding.*threshold|unsupported_claim_rate.*<|citation_accuracy.*0\.9[0-4]" butler_pc_core/cards/box3 \
  && { echo "BLOCK_GROUNDING_THRESHOLD_RELAXATION"; exit 1; } || echo "GROUNDING_THRESHOLD_RELAXATION_ZERO=true"

git diff --name-only 2>/dev/null | grep -E "^schemas/connect_loop/|^docs/ssot/connect_loop/" \
  && { echo "BLOCK_CONNECT_LOOP_CONTRACT_MODIFIED"; exit 1; } || echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true"

grep -RInE "/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY|raw_prompt|raw_output|raw_reference" evidence 2>/dev/null \
  && { echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1; } || echo "RAW_PATH_SECRET_LEAK_ZERO=true"

grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" . --exclude-dir=.git 2>/dev/null \
  | grep -v "scripts/verify_box3_v5_canonical_apply_v1_2.sh" \
  && { echo "BLOCK_CLAUDE_FOOTER"; exit 1; } || echo "CLAUDE_FOOTER_ZERO=true"

git diff --name-only 2>/dev/null | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' \
  && { echo "BLOCK_BINARY_ARTIFACT"; exit 1; } || echo "BINARY_ARTIFACT_ZERO=true"

echo "BOX3_V5_CANONICAL_APPLY_VERIFY_PASS=true"
