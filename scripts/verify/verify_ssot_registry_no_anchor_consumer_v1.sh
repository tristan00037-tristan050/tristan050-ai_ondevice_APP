#!/usr/bin/env bash
set -euo pipefail

SSOT_REGISTRY_NO_ANCHOR_CONSUMER_OK=0
finish() { echo "SSOT_REGISTRY_NO_ANCHOR_CONSUMER_OK=${SSOT_REGISTRY_NO_ANCHOR_CONSUMER_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REGISTRY="docs/ops/contracts/SSOT_REGISTRY_V1.txt"
test -f "$REGISTRY" || { echo "ERROR_CODE=ANCHOR_CONSUMER_FORBIDDEN"; exit 1; }

hit=$(grep -E '^SSOT=[^[:space:]]+[[:space:]]+CONSUMER=scripts/verify/verify_repo_contracts\.sh' "$REGISTRY" 2>/dev/null | head -n1 || true)
if [ -n "$hit" ]; then
  echo "ERROR_CODE=ANCHOR_CONSUMER_FORBIDDEN"
  echo "HIT_LINE=${hit}"
  exit 1
fi

SSOT_REGISTRY_NO_ANCHOR_CONSUMER_OK=1
exit 0
