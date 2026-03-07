#!/usr/bin/env bash
set -euo pipefail

VERIFY_NODE_ARGS_RUNTIME_V1_OK=0
trap 'echo "VERIFY_NODE_ARGS_RUNTIME_V1_OK=${VERIFY_NODE_ARGS_RUNTIME_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/VERIFY_NODE_ARGS_RUNTIME_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=VERIFY_NODE_ARGS_SSOT_MISSING"; exit 1; }
grep -q '^VERIFY_NODE_ARGS_RUNTIME_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=VERIFY_NODE_ARGS_SSOT_TOKEN_MISSING"; exit 1; }

RUNTIME_PATH="$(grep -E '^RUNTIME_PATH=' "$SSOT" | head -n1 | sed 's/^RUNTIME_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
[[ -n "$RUNTIME_PATH" ]] || { echo "ERROR_CODE=VERIFY_NODE_ARGS_RUNTIME_PATH_MISSING"; exit 1; }

RUNTIME="${ROOT}/${RUNTIME_PATH}"
[[ -f "$RUNTIME" ]] || { echo "ERROR_CODE=VERIFY_NODE_ARGS_RUNTIME_MISSING"; echo "HIT_PATH=$RUNTIME_PATH"; exit 1; }

node -e "require(process.argv[1])" "$RUNTIME" >/dev/null 2>&1 || {
  echo "ERROR_CODE=VERIFY_NODE_ARGS_RUNTIME_LOAD_FAILED"
  echo "HIT_PATH=$RUNTIME_PATH"
  exit 1
}

VERIFY_NODE_ARGS_RUNTIME_V1_OK=1
exit 0
