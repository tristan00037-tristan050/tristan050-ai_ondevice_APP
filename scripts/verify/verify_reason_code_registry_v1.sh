#!/usr/bin/env bash
set -euo pipefail

REASON_CODE_REGISTRY_PRESENT_OK=0
REASON_CODE_NOT_REGISTERED_BLOCK_OK=0
REASON_CODE_SINGLE_SOURCE_OK=0

cleanup() {
  echo "REASON_CODE_REGISTRY_PRESENT_OK=${REASON_CODE_REGISTRY_PRESENT_OK}"
  echo "REASON_CODE_NOT_REGISTERED_BLOCK_OK=${REASON_CODE_NOT_REGISTERED_BLOCK_OK}"
  echo "REASON_CODE_SINGLE_SOURCE_OK=${REASON_CODE_SINGLE_SOURCE_OK}"

  if [[ "$REASON_CODE_REGISTRY_PRESENT_OK" == "1" ]] && \
     [[ "$REASON_CODE_NOT_REGISTERED_BLOCK_OK" == "1" ]] && \
     [[ "$REASON_CODE_SINGLE_SOURCE_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

doc="docs/ops/contracts/REASON_CODE_REGISTRY_POLICY_V1.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "REASON_CODE_REGISTRY_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/agent/reason_code_gate_selftest_v1.cjs 2>&1)" || { echo "BLOCK: selftest failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -q '^REASON_CODE_REGISTRY_PRESENT_OK=1$' || exit 1
REASON_CODE_REGISTRY_PRESENT_OK=1
echo "$OUT" | grep -q '^REASON_CODE_NOT_REGISTERED_BLOCK_OK=1$' || exit 1
REASON_CODE_NOT_REGISTERED_BLOCK_OK=1
echo "$OUT" | grep -q '^REASON_CODE_SINGLE_SOURCE_OK=1$' || exit 1
REASON_CODE_SINGLE_SOURCE_OK=1

exit 0

