#!/usr/bin/env bash
set -euo pipefail

AI_GOLDEN_VECTORS_V2_OK=0
AI_DETERMINISM_FINGERPRINT_OK=0

cleanup() {
  echo "AI_GOLDEN_VECTORS_V2_OK=${AI_GOLDEN_VECTORS_V2_OK}"
  echo "AI_DETERMINISM_FINGERPRINT_OK=${AI_DETERMINISM_FINGERPRINT_OK}"

  if [[ "$AI_GOLDEN_VECTORS_V2_OK" == "1" ]] && \
     [[ "$AI_DETERMINISM_FINGERPRINT_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1) Policy document check
doc="docs/ops/contracts/AI_GOLDEN_VECTORS_V2_POLICY.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "AI_GOLDEN_VECTORS_V2_POLICY_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

# 2) SSOT file existence
ssot="scripts/ai/golden_vectors_v2.json"
test -f "$ssot" || { echo "BLOCK: missing SSOT file: $ssot"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 3) Run verification
OUT="$(node scripts/ai/verify_golden_vectors_v2.cjs "$ssot" 2>&1)" || { echo "BLOCK: verification failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -q '^AI_GOLDEN_VECTORS_V2_OK=1$' || exit 1
AI_GOLDEN_VECTORS_V2_OK=1
echo "$OUT" | grep -q '^AI_DETERMINISM_FINGERPRINT_OK=1$' || exit 1
AI_DETERMINISM_FINGERPRINT_OK=1

exit 0

