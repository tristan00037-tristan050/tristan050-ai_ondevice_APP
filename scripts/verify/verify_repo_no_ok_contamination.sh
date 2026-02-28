#!/usr/bin/env bash
set -euo pipefail

# Hardening++: tests/source(=테스트 코드)에서 *_OK=1 / OK=1 문자열/직접 출력 0건 (예외 없음)
# PASS에서만 OK_CONTAMINATION_REPO_GUARD_OK=1 출력

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# 스캔 대상: 레포 전체 중 tests 폴더들(언어 무관)
# node_modules/dist/coverage 제외
PAT1='\b[A-Z0-9_]+_OK=1\b'
PAT2='\bOK=1\b'

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

HITS=""
if have_rg; then
  HITS="$(rg -n --hidden --no-messages \
    --glob '!**/node_modules/**' \
    --glob '!**/dist/**' \
    --glob '!**/coverage/**' \
    --glob '**/tests/**' \
    -e "$PAT1" -e "$PAT2" . 2>/dev/null || true)"
else
  # grep fallback (PAT1/PAT2의 단어경계가 약해질 수 있으나 fail-closed 방향 유지)
  HITS="$(grep -RIn --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=coverage \
    -E '[A-Z0-9_]+_OK=1|(^|[^A-Za-z0-9_])OK=1([^A-Za-z0-9_]|$)' . 2>/dev/null | grep -E '/tests/' || true)"
fi

if [[ -n "${HITS}" ]]; then
  echo "FAIL: OK contamination detected in tests (must be 0)."
  echo "${HITS}"
  exit 1
fi

echo "OK_CONTAMINATION_REPO_GUARD_OK=1"

