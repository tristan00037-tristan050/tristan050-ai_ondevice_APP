#!/usr/bin/env bash
set -euo pipefail

AI_VARIANCE_OK=0
AI_OUTLIER_RATIO_OK=0

cleanup() {
  echo "AI_VARIANCE_OK=${AI_VARIANCE_OK}"
  echo "AI_OUTLIER_RATIO_OK=${AI_OUTLIER_RATIO_OK}"

  if [[ "$AI_VARIANCE_OK" == "1" ]] && \
     [[ "$AI_OUTLIER_RATIO_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1) Policy document check
doc="docs/ops/contracts/AI_VARIANCE_OUTLIER_POLICY_V1.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "AI_VARIANCE_OUTLIER_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 2) Run verification
OUT="$(node scripts/ai/verify_variance_outlier_v1.cjs 2>&1)" || { echo "BLOCK: verification failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -q '^AI_VARIANCE_OK=1$' || exit 1
AI_VARIANCE_OK=1
echo "$OUT" | grep -q '^AI_OUTLIER_RATIO_OK=1$' || exit 1
AI_OUTLIER_RATIO_OK=1

exit 0

