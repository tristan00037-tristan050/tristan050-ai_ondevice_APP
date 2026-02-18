#!/usr/bin/env bash
set -euo pipefail

# P5-AI-P0-01: Golden Vectors V2 Raw Text 0 V1
# - 판정만 (verify=판정만, build/install/download/network 금지)
# - raw text 금지, 배열 형태 금지, SSOT 존재 확인

AI_GOLDEN_VECTORS_V2_RAW_TEXT_0_OK=0
AI_GOLDEN_VECTORS_V2_NO_ARRAY_OK=0
AI_GOLDEN_VECTORS_V2_PRESENT_OK=0

trap 'echo "AI_GOLDEN_VECTORS_V2_RAW_TEXT_0_OK=${AI_GOLDEN_VECTORS_V2_RAW_TEXT_0_OK}";
      echo "AI_GOLDEN_VECTORS_V2_NO_ARRAY_OK=${AI_GOLDEN_VECTORS_V2_NO_ARRAY_OK}";
      echo "AI_GOLDEN_VECTORS_V2_PRESENT_OK=${AI_GOLDEN_VECTORS_V2_PRESENT_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="scripts/ai/golden_vectors_v2.json"
PATTERNS="docs/ops/contracts/AI_GOLDEN_VECTORS_V2_RAW_TEXT_FORBIDDEN_PATTERNS_V1.txt"

# 1) SSOT 존재 확인
[ -f "$SSOT" ] || { echo "BLOCK: missing SSOT: $SSOT"; exit 1; }
[ -s "$SSOT" ] || { echo "BLOCK: SSOT empty: $SSOT"; exit 1; }
AI_GOLDEN_VECTORS_V2_PRESENT_OK=1

# 2) 금지 패턴 SSOT 존재 확인
[ -f "$PATTERNS" ] || { echo "BLOCK: missing patterns SSOT: $PATTERNS"; exit 1; }
grep -q "AI_GOLDEN_VECTORS_V2_RAW_TEXT_FORBIDDEN_PATTERNS_V1_TOKEN=1" "$PATTERNS" || { echo "BLOCK: missing patterns token"; exit 1; }

# 3) 금지 패턴 검사 (raw text 직접 저장 금지)
# 주의: input.text는 허용 (meta-only input의 일부)
# 금지: raw_text, rawText 필드만 차단
if grep -Eiq '(^[[:space:]]*"raw_text"|^[[:space:]]*"rawText"|^[[:space:]]*'\''raw_text'\''|^[[:space:]]*'\''rawText'\''|raw_text[[:space:]]*:|rawText[[:space:]]*:)' "$SSOT" >/dev/null 2>&1; then
  echo "BLOCK: forbidden raw_text/rawText field detected in SSOT"
  grep -Eiq '(^[[:space:]]*"raw_text"|^[[:space:]]*"rawText"|^[[:space:]]*'\''raw_text'\''|^[[:space:]]*'\''rawText'\''|raw_text[[:space:]]*:|rawText[[:space:]]*:)' "$SSOT" | head -n 10
  exit 1
fi

AI_GOLDEN_VECTORS_V2_RAW_TEXT_0_OK=1

# 4) 배열 형태의 raw text 저장 금지 (raw_texts, rawTexts 등)
if grep -qiE "(raw_texts|rawTexts)" "$SSOT"; then
  echo "BLOCK: array form of raw text detected (raw_texts/rawTexts)"
  exit 1
fi

AI_GOLDEN_VECTORS_V2_NO_ARRAY_OK=1

exit 0

