#!/usr/bin/env bash
set -euo pipefail

DIR="docs/ops/contracts"
[[ -d "$DIR" ]] || { echo "FAIL: missing $DIR"; exit 1; }

# placeholder 계열만 금지한다. (PASS requires의 *_OK=1 같은 설명 문구는 허용)
PAT='(PASTE_|<PASTE|TODO|\(여기에|PLACEHOLDER)'

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
HITS=""
if have_rg; then
  HITS="$(rg -n --no-messages -e "${PAT}" "${DIR}" || true)"
  # *_OK=1 패턴은 제외 (설명 문구 허용)
  if [[ -n "${HITS}" ]]; then
    HITS="$(echo "${HITS}" | grep -vE '_OK=1' || true)"
  fi
else
  HITS="$(grep -RIn -E "${PAT}" "${DIR}" || true)"
  # *_OK=1 패턴은 제외 (설명 문구 허용)
  if [[ -n "${HITS}" ]]; then
    HITS="$(echo "${HITS}" | grep -vE '_OK=1' || true)"
  fi
fi

if [[ -n "${HITS}" ]]; then
  echo "FAIL: SSOT placeholders found (pattern: ${PAT})"
  echo "${HITS}"
  exit 1
fi

echo "SSOT_PLACEHOLDER_GUARD_OK=1"

