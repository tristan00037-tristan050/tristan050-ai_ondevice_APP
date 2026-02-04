#!/usr/bin/env bash
set -euo pipefail

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=0
cleanup(){ echo "CANONICALIZE_SHARED_SINGLE_SOURCE_OK=${CANONICALIZE_SHARED_SINGLE_SOURCE_OK}"; }
trap cleanup EXIT

command -v rg >/dev/null 2>&1 || { echo "FAIL: rg not found"; exit 1; }

# "canonicalize" 또는 "JCS" 구현 흔적을 스캔해 중복 구현을 차단
HITS="$(rg -n --no-messages '(jcsCanonicalize|JSON Canonicalization Scheme|RFC 8785|canonicalize\()' . \
  -g'*.ts' -g'*.js' \
  -g'!packages/common/src/crypto/jcs.ts' \
  -g'!packages/common/test/jcs.test.ts' \
  || true)"

if [[ -n "$HITS" ]]; then
  echo "FAIL: JCS/canonicalize duplicate implementation detected (single source required)"
  echo "$HITS"
  exit 1
fi

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1
exit 0

