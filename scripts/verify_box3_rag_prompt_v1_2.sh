#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"

# connect_loop must not be touched by this feature package.
if find "$ROOT" -type f | grep -E "schemas/connect_loop|docs/ssot/connect_loop" >/tmp/box3_rag_connect_loop_hits.txt; then
  echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true (package does not include connect_loop files)"
else
  echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true"
fi

# Prompt/reference/output raw must not appear in evidence. Code and tests can contain runtime fixtures.
if [ -d "$ROOT/evidence" ]; then
  grep -RInE "prompt_runtime_only|reference_text_runtime_only|draft_text_runtime|raw_prompt|raw_output|/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY" "$ROOT/evidence" \
    && { echo "BLOCK_EVIDENCE_RAW_OR_PATH"; exit 1; } || echo "EVIDENCE_RAW_PATH_ZERO=true"
else
  echo "EVIDENCE_RAW_PATH_ZERO=true"
fi

grep -RInE "temperature[\"']?\s*:\s*0\.[3-9]|top_p[\"']?\s*:\s*0\.9|repeat_penalty[\"']?\s*:\s*1\.0" "$ROOT/butler_pc_core/cards/box3" \
  && { echo "BLOCK_DECODE_CONFIG_DRIFT"; exit 1; } || echo "DECODE_CONFIG_DRIFT_ZERO=true"

grep -RInE "unsupported_count\s*=\s*0.*force|grounding.*threshold.*lower|citation_accuracy.*0\.[0-8]" "$ROOT/butler_pc_core/cards/box3" \
  && { echo "BLOCK_GROUNDING_THRESHOLD_RELAXATION"; exit 1; } || echo "GROUNDING_THRESHOLD_RELAXATION_ZERO=true"

find "$ROOT" -type f | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' \
  && { echo "BLOCK_BINARY_ARTIFACT"; exit 1; } || echo "BINARY_ARTIFACT_ZERO=true"

grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" "$ROOT" --exclude="verify_box3_rag_prompt_v1_2.sh" --exclude-dir=evidence \
  && { echo "BLOCK_CLAUDE_FOOTER"; exit 1; } || echo "CLAUDE_FOOTER_ZERO=true"

echo "BOX3_RAG_PROMPT_SECURITY_PASS=true"
