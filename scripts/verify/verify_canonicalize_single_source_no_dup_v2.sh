#!/usr/bin/env bash
set -euo pipefail

# P5-AI-P0-02: Canonicalize Single Source No Duplication V2
# - 판정만 (verify=판정만, build/install/download/network 금지)
# - canonicalize_v2.cjs 복제본 탐지

CANONICALIZE_V2_SSOT_OK=0
CANONICALIZE_V2_NO_DUP_OK=0

trap 'echo "CANONICALIZE_V2_SSOT_OK=${CANONICALIZE_V2_SSOT_OK}";
      echo "CANONICALIZE_V2_NO_DUP_OK=${CANONICALIZE_V2_NO_DUP_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="packages/common/meta_only/canonicalize_v2.cjs"

# 1) SSOT 존재 확인
[ -f "$SSOT" ] || { echo "BLOCK: missing SSOT: $SSOT"; exit 1; }
[ -s "$SSOT" ] || { echo "BLOCK: SSOT empty: $SSOT"; exit 1; }
CANONICALIZE_V2_SSOT_OK=1

# 2) 복제본 탐지 (canonicalizeMetaRecordV2 함수 구현이 다른 곳에 있으면 BLOCK)
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

if have_rg; then
  HITS="$(rg -n --hidden --no-messages \
    --glob '!**/node_modules/**' \
    --glob '!**/dist/**' \
    --glob '!**/coverage/**' \
    -e 'function\s+canonicalizeMetaRecordV2\s*\(' \
    -e 'const\s+canonicalizeMetaRecordV2\s*=\s*' \
    -e 'export\s+function\s+canonicalizeMetaRecordV2\s*\(' \
    . || true)"
else
  PAT='(function\s+canonicalizeMetaRecordV2\s*\(|const\s+canonicalizeMetaRecordV2\s*=|export\s+function\s+canonicalizeMetaRecordV2\s*\()'
  HITS="$(grep -RIn \
    --exclude-dir=node_modules \
    --exclude-dir=dist \
    --exclude-dir=coverage \
    -E "$PAT" \
    . 2>/dev/null || true)"
fi

# SSOT 경로 외 히트만 남김
ALLOW_PATTERN="^\./${SSOT}"
BAD=""
while IFS= read -r line; do
  if [[ -n "$line" ]] && ! echo "$line" | grep -qE "$ALLOW_PATTERN"; then
    if [[ -z "$BAD" ]]; then
      BAD="$line"
    else
      BAD="$BAD"$'\n'"$line"
    fi
  fi
done <<< "$HITS"

if [[ -n "$BAD" ]]; then
  echo "BLOCK: canonicalize_v2 duplicate implementation detected (must be single-source)"
  echo "$BAD"
  exit 1
fi

CANONICALIZE_V2_NO_DUP_OK=1
exit 0

