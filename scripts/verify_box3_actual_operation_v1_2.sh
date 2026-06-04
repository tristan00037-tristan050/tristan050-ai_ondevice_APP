#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"

grep -RInE "localStorage|sessionStorage|indexedDB" butler_pc_core tests 2>/dev/null \
  && { echo "BLOCK_BROWSER_STORAGE"; exit 1; } || echo "BROWSER_STORAGE_ZERO=true"

grep -RInE "fetch\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket|requests\.|httpx\.|aiohttp\." butler_pc_core tests 2>/dev/null \
  | grep -v "127.0.0.1:8765" \
  && { echo "BLOCK_NON_LOCAL_NETWORK"; exit 1; } || echo "NON_LOCAL_NETWORK_ZERO=true"

grep -RInE "APPROVED_FOR_PRODUCTION|production ready|release ready|PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL.*SELF_CHECK_PASS" butler_pc_core tests evidence 2>/dev/null \
  && { echo "BLOCK_FORBIDDEN_CLAIM"; exit 1; } || echo "FORBIDDEN_CLAIM_ZERO=true"

grep -RInE "raw_prompt|raw_reference|raw_draft|/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY" evidence butler_pc_core/cards/box3 tests/cards/box3 2>/dev/null \
  | grep -v "raw_saved_zero" \
  | grep -v "raw_text_logged" \
  | grep -v "path_digest" \
  | grep -v "path_ref" \
  && { echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1; } || echo "RAW_PATH_SECRET_LEAK_ZERO=true"

find . -type f | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' \
  && { echo "BLOCK_BINARY_ARTIFACT"; exit 1; } || echo "BINARY_ARTIFACT_ZERO=true"

grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" butler_pc_core tests evidence README_MAINDEV_RESULT.md APPLY_GUIDE.md PR_BODY_TEMPLATE.md 2>/dev/null \
  && { echo "BLOCK_CLAUDE_FOOTER"; exit 1; } || echo "CLAUDE_FOOTER_ZERO=true"
