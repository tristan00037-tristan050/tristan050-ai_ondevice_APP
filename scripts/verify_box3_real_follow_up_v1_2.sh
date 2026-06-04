#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"

if find "$ROOT" -path "*/real_enablement/*" -type f | grep -q .; then
  echo "BLOCK_PARALLEL_REAL_ENABLEMENT_SUBPACKAGE"; exit 1
else
  echo "PARALLEL_REAL_ENABLEMENT_SUBPACKAGE_ZERO=true"
fi
if grep -RInE "reference_docs=|ground_claims\(.*\).*=" "$ROOT/butler_pc_core/cards/box3" 2>/dev/null; then
  echo "BLOCK_DRIFTED_SIGNATURE_USAGE"; exit 1
else
  echo "DRIFTED_SIGNATURE_USAGE_ZERO=true"
fi
if grep -RInE "PASS_BOX3_REAL([^_A-Z]|$)|RUNTIME_REAL_APPROVED|REAL_APPROVED" "$ROOT/butler_pc_core" "$ROOT/tests" 2>/dev/null; then
  echo "BLOCK_FORBIDDEN_STATUS_LABEL"; exit 1
else
  echo "FORBIDDEN_STATUS_LABEL_ZERO=true"
fi
if grep -RInE "schemas/connect_loop|docs/ssot/connect_loop" "$ROOT/MANIFEST.json" "$ROOT/FULL_SHA256_MANIFEST.txt" 2>/dev/null; then
  echo "BLOCK_CONNECT_LOOP_CONTRACT_INCLUDED"; exit 1
else
  echo "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO=true"
fi
if grep -RInE "sk-proj-|BEGIN PRIVATE KEY|/Users/|/home/|/Volumes/|raw_prompt|raw_answer|raw_source_text|absolute_local_path" "$ROOT" --exclude-dir=.git --exclude=security.py --exclude=verify_box3_real_follow_up_v1_2.sh 2>/dev/null; then
  echo "BLOCK_RAW_PATH_SECRET_LEAK"; exit 1
else
  echo "RAW_PATH_SECRET_SCAN_ZERO=true"
fi
if find "$ROOT" -type f | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' | grep -q .; then
  echo "BLOCK_BINARY_ARTIFACT"; exit 1
else
  echo "BINARY_ARTIFACT_ZERO=true"
fi
if grep -RIn "Generated with Claude Code\|Co-Authored-By: Claude" "$ROOT" --exclude=verify_box3_real_follow_up_v1_2.sh 2>/dev/null; then
  echo "BLOCK_CLAUDE_FOOTER"; exit 1
else
  echo "CLAUDE_FOOTER_ZERO=true"
fi
