#!/usr/bin/env bash
set -euo pipefail

AI_ENERGY_PROXY_DEFINITION_SSOT_OK=0
AI_ENERGY_MEASUREMENTS_SOURCE_OK=0
AI_ENERGY_STABILITY_OK=0

cleanup() {
  echo "AI_ENERGY_PROXY_DEFINITION_SSOT_OK=${AI_ENERGY_PROXY_DEFINITION_SSOT_OK}"
  echo "AI_ENERGY_MEASUREMENTS_SOURCE_OK=${AI_ENERGY_MEASUREMENTS_SOURCE_OK}"
  echo "AI_ENERGY_STABILITY_OK=${AI_ENERGY_STABILITY_OK}"

  if [[ "$AI_ENERGY_PROXY_DEFINITION_SSOT_OK" == "1" ]] && \
     [[ "$AI_ENERGY_MEASUREMENTS_SOURCE_OK" == "1" ]] && \
     [[ "$AI_ENERGY_STABILITY_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1) Policy document check
doc="docs/ops/contracts/AI_ENERGY_PROXY_POLICY_V1.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "AI_ENERGY_PROXY_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 2) Measurements file check
measurements_file="scripts/ai/fixtures/energy_proxy_measurements_v1.json"
test -f "$measurements_file" || { echo "BLOCK: missing measurements file: $measurements_file"; exit 1; }

# 3) Run verification with file input
OUT="$(node scripts/ai/verify_energy_proxy_stability_v1.cjs --measurements_json "$measurements_file" 2>&1)" || { echo "BLOCK: verification failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -q '^AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1$' || exit 1
AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1
echo "$OUT" | grep -q '^AI_ENERGY_MEASUREMENTS_SOURCE_OK=1$' || exit 1
AI_ENERGY_MEASUREMENTS_SOURCE_OK=1
echo "$OUT" | grep -q '^AI_ENERGY_STABILITY_OK=1$' || exit 1
AI_ENERGY_STABILITY_OK=1

exit 0

