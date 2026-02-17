#!/usr/bin/env bash
set -euo pipefail

INSTRUCTION_RAW_0_OK=0
INSTRUCTION_HASH_ONLY_OK=0
INSTRUCTION_LAYER_REGISTRY_OK=0

cleanup() {
  echo "INSTRUCTION_RAW_0_OK=${INSTRUCTION_RAW_0_OK}"
  echo "INSTRUCTION_HASH_ONLY_OK=${INSTRUCTION_HASH_ONLY_OK}"
  echo "INSTRUCTION_LAYER_REGISTRY_OK=${INSTRUCTION_LAYER_REGISTRY_OK}"

  if [[ "$INSTRUCTION_RAW_0_OK" == "1" ]] && \
     [[ "$INSTRUCTION_HASH_ONLY_OK" == "1" ]] && \
     [[ "$INSTRUCTION_LAYER_REGISTRY_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

doc="docs/ops/contracts/INSTRUCTION_LAYERS_POLICY_V1.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "INSTRUCTION_LAYERS_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/agent/instruction_layers_selftest_v1.cjs 2>&1)" || { echo "BLOCK: selftest failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -q '^INSTRUCTION_RAW_0_OK=1$' || exit 1
INSTRUCTION_RAW_0_OK=1
echo "$OUT" | grep -q '^INSTRUCTION_HASH_ONLY_OK=1$' || exit 1
INSTRUCTION_HASH_ONLY_OK=1
echo "$OUT" | grep -q '^INSTRUCTION_LAYER_REGISTRY_OK=1$' || exit 1
INSTRUCTION_LAYER_REGISTRY_OK=1

exit 0

