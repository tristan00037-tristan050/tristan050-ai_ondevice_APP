#!/usr/bin/env bash
set -euo pipefail

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=0
cleanup(){ echo "CANONICALIZE_SHARED_SINGLE_SOURCE_OK=${CANONICALIZE_SHARED_SINGLE_SOURCE_OK}"; }
trap cleanup EXIT

# "canonicalize" 또는 "JCS" 구현 흔적을 스캔해 중복 구현을 차단 (rg 없거나 동작 안 하면 grep+find 폴백)
have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
if have_rg; then
  HITS="$(rg -n --no-messages '(jcsCanonicalize|JSON Canonicalization Scheme|RFC 8785|canonicalize\()' . \
    -g'*.ts' -g'*.js' \
    -g'!packages/common/src/crypto/jcs.ts' \
    -g'!packages/common/test/jcs.test.ts' \
    || true)"
else
  HITS="$(find . -type f \( -name '*.ts' -o -name '*.js' \) \
    ! -path '*node_modules*' \
    ! -path './packages/common/src/crypto/jcs.ts' ! -path './packages/common/test/jcs.test.ts' \
    -exec grep -nE '(jcsCanonicalize|JSON Canonicalization Scheme|RFC 8785|canonicalize\()' {} + 2>/dev/null || true)"
fi

if [[ -n "$HITS" ]]; then
  echo "FAIL: JCS/canonicalize duplicate implementation detected (single source required)"
  echo "$HITS"
  exit 1
fi

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1
exit 0

