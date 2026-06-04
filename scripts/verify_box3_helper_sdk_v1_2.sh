#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"

SCAN_CODE="$ROOT/butler_pc_core $ROOT/tests"
SCAN_EVIDENCE="$ROOT/evidence"

grep -RInE "schemas/connect_loop|docs/ssot/connect_loop" $SCAN_CODE 2>/dev/null \
  && { echo "BLOCK_CONNECT_LOOP_CONTRACT_MIXED"; exit 1; } || echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true"

grep -RInE "helper4_grounding.*model_stack_supported.*True|helper7_table_figure.*model_stack_supported.*True|helper8_company_style.*model_stack_supported.*True" "$ROOT/butler_pc_core/cards/box3" \
  && { echo "BLOCK_HELPER_SDK_STACK_ATTEMPT"; exit 1; } || echo "HELPER_SDK_STACK_ATTEMPT_ZERO=true"

grep -RInE "be18e3cc" "$ROOT/butler_pc_core/cards/box3" \
  && { echo "BLOCK_HELPER8_NON_CANONICAL_SHA_LITERAL"; exit 1; } || echo "HELPER8_NON_CANONICAL_LITERAL_ZERO=true"

grep -RInE "localStorage|sessionStorage|indexedDB|sendBeacon|WebSocket|fetch\(|axios\.|XMLHttpRequest" $SCAN_CODE 2>/dev/null \
  && { echo "BLOCK_BROWSER_OR_NETWORK_SURFACE"; exit 1; } || echo "BROWSER_NETWORK_SURFACE_ZERO=true"

grep -RInE "raw prompt|raw output|/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY" $SCAN_EVIDENCE "$ROOT/tests" 2>/dev/null \
  && { echo "BLOCK_RAW_PATH_SECRET_EVIDENCE"; exit 1; } || echo "RAW_PATH_SECRET_EVIDENCE_ZERO=true"

find "$ROOT" -type f \( -name "*.safetensors" -o -name "*.gguf" -o -name "*.bin" -o -name "*.npy" -o -name "*.pkl" \) | grep . \
  && { echo "BLOCK_BINARY_ARTIFACT"; exit 1; } || echo "BINARY_ARTIFACT_ZERO=true"

grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" $SCAN_CODE "$ROOT/evidence" "$ROOT/docs" 2>/dev/null \
  && { echo "BLOCK_CLAUDE_FOOTER"; exit 1; } || echo "CLAUDE_FOOTER_ZERO=true"
