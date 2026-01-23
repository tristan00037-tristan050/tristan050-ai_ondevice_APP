#!/usr/bin/env bash
set -euo pipefail

# Hardening++ SSOT 문서 게이트:
# - placeholder/TODO/PASTE_* 0
# - 체크리스트 미체크([ ]) 0
# PASS에서만 SSOT_PLACEHOLDER_GUARD_OK=1 출력

DIR="docs/ops/contracts"
[[ -d "$DIR" ]] || { echo "FAIL: missing $DIR"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1; }

# 실제 placeholder만 잡기: PASTE_*, <PASTE*, TODO + (URL|LINK|HERE|UPDATE), PLACEHOLDER + (URL|LINK|HERE|UPDATE)
PAT_PLACEHOLDER='(PASTE_|<PASTE|TODO\s+(URL|LINK|HERE|UPDATE)|PLACEHOLDER\s+(URL|LINK|HERE|UPDATE))'
PAT_UNCHECKED='\[ \]'

HITS1=""
HITS2=""

if have_rg; then
  HITS1="$(rg -n --no-messages -e "$PAT_PLACEHOLDER" "$DIR" || true)"
  HITS2="$(rg -n --no-messages -e "$PAT_UNCHECKED" "$DIR" || true)"
else
  HITS1="$(grep -RIn -E "$PAT_PLACEHOLDER" "$DIR" || true)"
  HITS2="$(grep -RIn -E '\[ \]' "$DIR" || true)"
fi

if [[ -n "$HITS1" ]]; then
  echo "FAIL: SSOT placeholders found"
  echo "$HITS1"
  exit 1
fi

if [[ -n "$HITS2" ]]; then
  echo "FAIL: SSOT unchecked checklist found ([ ])"
  echo "$HITS2"
  exit 1
fi

echo "SSOT_PLACEHOLDER_GUARD_OK=1"

