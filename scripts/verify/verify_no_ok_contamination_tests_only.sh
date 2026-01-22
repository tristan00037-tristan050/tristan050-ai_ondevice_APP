#!/usr/bin/env bash
set -euo pipefail

PAT='\b[A-Z0-9_]+_OK=1\b'

# tests 경로만 검사한다. docs는 검사 대상이 아니다.
# node_modules/dist/coverage 같은 큰 폴더는 제외한다.
scan_with_rg() {
  rg -n --hidden --no-messages \
    --glob '!**/node_modules/**' \
    --glob '!**/dist/**' \
    --glob '!**/coverage/**' \
    --glob '**/tests/**' \
    -e "${PAT}" .
}

scan_with_grep() {
  # grep은 \b가 약해서, 단어 경계 대신 "대문자/숫자/_ + _OK=1" 형태로 잡는다.
  grep -RIn --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=coverage \
    -E '[A-Z0-9_]+_OK=1' . | grep -E '/tests/' || true
}

HITS=""
if command -v rg >/dev/null 2>&1; then
  HITS="$(scan_with_rg || true)"
else
  HITS="$(scan_with_grep || true)"
fi

if [[ -n "${HITS}" ]]; then
  echo "FAIL: tests contamination found (pattern: ${PAT})"
  echo "${HITS}"
  exit 1
fi

echo "OK_CONTAMINATION_TESTS_ONLY_OK=1"

