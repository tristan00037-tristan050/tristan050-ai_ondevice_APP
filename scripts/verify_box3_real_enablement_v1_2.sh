#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"

if git diff --name-only 2>/dev/null | grep -E '^schemas/connect_loop/|^docs/ssot/connect_loop/' >/dev/null; then
  echo "BLOCK_CONNECT_LOOP_CONTRACT_MODIFIED"; exit 1
else
  echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true"
fi

if grep -RInE 'localStorage|sessionStorage|indexedDB' butler-desktop/src src 2>/dev/null | grep -v node_modules >/dev/null; then
  echo "BLOCK_BROWSER_STORAGE"; exit 1
else
  echo "BROWSER_STORAGE_ZERO=true"
fi

if grep -RInE 'fetch\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket' butler-desktop/src src 2>/dev/null | grep -v '127.0.0.1:8765' >/dev/null; then
  echo "BLOCK_NON_LOCAL_NETWORK"; exit 1
else
  echo "NON_LOCAL_NETWORK_ZERO=true"
fi

if grep -RInE 'mock_or_stub=True|loader_name=.mock|loader_name=.stub|BLOCK_MOCK_RUNNER_FOR_REAL.*PASS' butler_pc_core tests scripts 2>/dev/null | grep -v 'BLOCK_MOCK_RUNNER_FOR_REAL' >/dev/null; then
  echo "BLOCK_MOCK_AS_REAL"; exit 1
else
  echo "MOCK_REAL_CLAIM_ZERO=true"
fi

if grep -RInE 'base_model_sha256_full.*(60b9baee|1ce4b49a)|sha256_full.*(60b9baee|1ce4b49a)' butler_pc_core evidence 2>/dev/null >/dev/null; then
  echo "BLOCK_PREFIX_USED_AS_SEAL"; exit 1
else
  echo "PREFIX_AS_SEAL_ZERO=true"
fi

if grep -RInE 'raw_reference|raw_draft|raw_text[^_a-zA-Z]|/Users/|/home/|/Volumes/|sk-proj-|BEGIN .*PRIVATE KEY' evidence 2>/dev/null | grep -v 'raw_text_logged' | grep -v 'runtime_only' >/dev/null; then
  echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1
elif grep -RInE 'raw_reference|raw_draft|sk-proj-|BEGIN .*PRIVATE KEY' butler_pc_core/cards/box3 2>/dev/null | grep -v 'raw_text_logged' | grep -v 'runtime_only' | grep -v 'real_contracts.py' >/dev/null; then
  echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1
else
  echo "RAW_PATH_SECRET_LEAK_ZERO=true"
fi

if find . -type f | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' >/dev/null; then
  echo "BLOCK_BINARY_ARTIFACT"; exit 1
else
  echo "BINARY_ARTIFACT_ZERO=true"
fi

if grep -RIn 'Generated with Claude Code\|Co-Authored-By: Claude' . --exclude-dir=.git 2>/dev/null | grep -v 'verify_box3_real_enablement_v1_2.sh' >/dev/null; then
  echo "BLOCK_CLAUDE_FOOTER"; exit 1
else
  echo "CLAUDE_FOOTER_ZERO=true"
fi
