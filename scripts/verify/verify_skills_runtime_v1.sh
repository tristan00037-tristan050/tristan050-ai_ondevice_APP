#!/usr/bin/env bash
set -euo pipefail

SKILLS_MANIFEST_PRESENT_OK=0
SKILLS_CAPABILITY_GATE_BLOCK_OK=0
SKILLS_META_ONLY_PROOF_OK=0
SKILLS_META_ONLY_REQUIRED_OK=0

cleanup() {
  echo "SKILLS_MANIFEST_PRESENT_OK=${SKILLS_MANIFEST_PRESENT_OK}"
  echo "SKILLS_CAPABILITY_GATE_BLOCK_OK=${SKILLS_CAPABILITY_GATE_BLOCK_OK}"
  echo "SKILLS_META_ONLY_PROOF_OK=${SKILLS_META_ONLY_PROOF_OK}"
  echo "SKILLS_META_ONLY_REQUIRED_OK=${SKILLS_META_ONLY_REQUIRED_OK}"

  if [[ "$SKILLS_MANIFEST_PRESENT_OK" == "1" ]] && \
     [[ "$SKILLS_CAPABILITY_GATE_BLOCK_OK" == "1" ]] && \
     [[ "$SKILLS_META_ONLY_PROOF_OK" == "1" ]] && \
     [[ "$SKILLS_META_ONLY_REQUIRED_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Policy document check
doc="docs/ops/contracts/SKILLS_RUNTIME_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "SKILLS_CAPABILITY_GATE_REQUIRED=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

# Manifest file check
manifest="scripts/agent/skills_manifest_v1.json"
[ -f "$manifest" ] || { echo "BLOCK: missing $manifest"; exit 1; }
SKILLS_MANIFEST_PRESENT_OK=1

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/agent/skills_runtime_selftest_v1.cjs 2>&1)" || { echo "BLOCK: skills runtime selftest failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -nE '^SKILLS_MANIFEST_PRESENT_OK=1$' >/dev/null || exit 1
SKILLS_MANIFEST_PRESENT_OK=1

echo "$OUT" | grep -nE '^SKILLS_CAPABILITY_GATE_BLOCK_OK=1$' >/dev/null || exit 1
SKILLS_CAPABILITY_GATE_BLOCK_OK=1

echo "$OUT" | grep -nE '^SKILLS_META_ONLY_PROOF_OK=1$' >/dev/null || exit 1
SKILLS_META_ONLY_PROOF_OK=1

echo "$OUT" | grep -nE '^SKILLS_META_ONLY_REQUIRED_OK=1$' >/dev/null || exit 1
SKILLS_META_ONLY_REQUIRED_OK=1

exit 0

