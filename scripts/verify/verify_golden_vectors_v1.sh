#!/usr/bin/env bash
set -euo pipefail

AI_GOLDEN_VECTORS_PRESENT_V1_OK=0
AI_GOLDEN_VECTORS_D0_STABLE_V1_OK=0
AI_GOLDEN_VECTORS_PACK_IMPACT_V1_OK=0
AI_GOLDEN_VECTORS_BUDGET_MEASURED_V1_OK=0
AI_GOLDEN_VECTORS_NO_RAW_OK=0
trap '
echo "AI_GOLDEN_VECTORS_PRESENT_V1_OK=$AI_GOLDEN_VECTORS_PRESENT_V1_OK";
echo "AI_GOLDEN_VECTORS_D0_STABLE_V1_OK=$AI_GOLDEN_VECTORS_D0_STABLE_V1_OK";
echo "AI_GOLDEN_VECTORS_PACK_IMPACT_V1_OK=$AI_GOLDEN_VECTORS_PACK_IMPACT_V1_OK";
echo "AI_GOLDEN_VECTORS_BUDGET_MEASURED_V1_OK=$AI_GOLDEN_VECTORS_BUDGET_MEASURED_V1_OK";
echo "AI_GOLDEN_VECTORS_NO_RAW_OK=$AI_GOLDEN_VECTORS_NO_RAW_OK";
' EXIT

# vectors file must exist
f="ai/golden_vectors/v1.ndjson"
[ -f "$f" ] || { echo "BLOCK: missing $f"; exit 1; }
AI_GOLDEN_VECTORS_PRESENT_V1_OK=1

command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

out="$(MODEL_A=demoA MODEL_B=demoB INTENT=ALGO_CORE_THREE_BLOCKS node scripts/ai/run_golden_vectors_v1.mjs 2>&1 || true)"
echo "$out" | grep -q "^ERROR_CODE=" && { echo "$out" | grep "^ERROR_CODE=" | head -1; exit 1; }

# no raw-like tokens in vectors file (coarse, fail-closed)
if grep -qE '"(prompt|raw|messages|document_body|request_id|ts_utc|nonce|manifest|run_id)"[[:space:]]*:' "$f"; then
  echo "BLOCK: banned keys present in vectors file"
  exit 1
fi
AI_GOLDEN_VECTORS_NO_RAW_OK=1

d0="$(echo "$out" | grep "^GV_D0_STABLE_ALL=" | cut -d= -f2 | head -1)"
pi="$(echo "$out" | grep "^GV_PACK_IMPACT_ANY=" | cut -d= -f2 | head -1)"
bm="$(echo "$out" | grep "^GV_BUDGET_MEASURED_ALL=" | cut -d= -f2 | head -1)"

[ "$d0" = "1" ] || { echo "BLOCK: D0 unstable"; exit 1; }
[ "$pi" = "1" ] || { echo "BLOCK: pack impact missing"; exit 1; }
[ "$bm" = "1" ] || { echo "BLOCK: budget not measured"; exit 1; }

AI_GOLDEN_VECTORS_D0_STABLE_V1_OK=1
AI_GOLDEN_VECTORS_PACK_IMPACT_V1_OK=1
AI_GOLDEN_VECTORS_BUDGET_MEASURED_V1_OK=1
exit 0

