#!/usr/bin/env bash
set -euo pipefail

VERIFY_NODE_ARGS_RUNTIME_V1_OK=0
trap 'echo "VERIFY_NODE_ARGS_RUNTIME_V1_OK=${VERIFY_NODE_ARGS_RUNTIME_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/VERIFY_NODE_ARGS_RUNTIME_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=VERIFY_NODE_ARGS_SSOT_MISSING"; exit 1; }
grep -q '^VERIFY_NODE_ARGS_RUNTIME_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=VERIFY_NODE_ARGS_SSOT_TOKEN_MISSING"; exit 1; }

RUNTIME="${ROOT}/tools/verify-runtime/node_args_v1.cjs"
[[ -s "$RUNTIME" ]] || { echo "ERROR_CODE=VERIFY_NODE_ARGS_RUNTIME_MISSING"; exit 1; }

if ! node -e "require('$RUNTIME')" 2>/dev/null; then
  echo "ERROR_CODE=VERIFY_NODE_ARGS_RUNTIME_LOAD_FAILED"
  exit 1
fi

VERIFY_NODE_ARGS_RUNTIME_V1_OK=1
exit 0
