#!/usr/bin/env bash
set -euo pipefail

DIR="docs/ops/contracts"
[[ -d "$DIR" ]] || { echo "FAIL: missing $DIR"; exit 1; }

# placeholder 계열만 금지한다. (PASS requires의 *_OK=1 같은 설명 문구는 허용)
PAT='(PASTE_|<PASTE|TODO|PLACEHOLDER)'

HITS=""
if command -v rg >/dev/null 2>&1; then
  HITS="$(rg -n --no-messages -e "${PAT}" "${DIR}" || true)"
else
  HITS="$(grep -RIn -E "${PAT}" "${DIR}" || true)"
fi

if [[ -n "${HITS}" ]]; then
  echo "FAIL: SSOT placeholders found (pattern: ${PAT})"
  echo "${HITS}"
  exit 1
fi

echo "SSOT_PLACEHOLDER_GUARD_OK=1"

