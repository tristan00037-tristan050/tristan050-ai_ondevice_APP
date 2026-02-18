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
# BLOCK only when it appears as a JSON key declaration: "raw_text":
# 스캔 대상: golden vectors v2 데이터 파일
SCAN_TARGETS=("$SSOT")

# 3-1) raw_text 필드 키 검사
if grep -EIn '"raw_text"[[:space:]]*:' "${SCAN_TARGETS[@]}" >/dev/null 2>&1; then
  echo "BLOCK: forbidden field key raw_text present"
  exit 1
fi

# 3-2) rawText 필드 키 검사
if grep -EIn '"rawText"[[:space:]]*:' "${SCAN_TARGETS[@]}" >/dev/null 2>&1; then
  echo "BLOCK: forbidden field key rawText present"
  exit 1
fi

AI_GOLDEN_VECTORS_V2_RAW_TEXT_0_OK=1

# 4) 배열 형태의 raw text 저장 금지 (raw_texts, rawTexts 필드 키만 차단)
if grep -EIn '"raw_texts"[[:space:]]*:' "${SCAN_TARGETS[@]}" >/dev/null 2>&1; then
  echo "BLOCK: forbidden field key raw_texts present"
  exit 1
fi

if grep -EIn '"rawTexts"[[:space:]]*:' "${SCAN_TARGETS[@]}" >/dev/null 2>&1; then
  echo "BLOCK: forbidden field key rawTexts present"
  exit 1
fi

AI_GOLDEN_VECTORS_V2_NO_ARRAY_OK=1

exit 0

