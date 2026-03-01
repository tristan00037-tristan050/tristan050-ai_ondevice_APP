#!/usr/bin/env bash
set -euo pipefail

OUTPUT_ROOT_SSOT_V1_OK=0
CI_DOCS_WRITE_BLOCK_V1_OK=0

finish() {
  echo "OUTPUT_ROOT_SSOT_V1_OK=${OUTPUT_ROOT_SSOT_V1_OK}"
  echo "CI_DOCS_WRITE_BLOCK_V1_OK=${CI_DOCS_WRITE_BLOCK_V1_OK}"
}
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/OUTPUT_ROOT_SSOT_V1.txt"

test -f "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }
grep -q '^OUTPUT_ROOT_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_TOKEN_MISSING"; exit 1; }

# OUT_ROOT 허용값 검사
v="$(grep -E '^OUT_ROOT=' "$SSOT" | tail -n1 | cut -d= -f2- | tr -d '\r')"
case "$v" in out|docs) ;; *) echo "ERROR_CODE=OUT_ROOT_INVALID"; exit 1;; esac

# CI에서는 docs write(추적/비추적) 전부 BLOCK
if [ "${CI:-}" = "true" ]; then
  st="$(git status --porcelain)"
  if echo "$st" | grep -qE 'docs/'; then
    echo "ERROR_CODE=CI_DOCS_WRITE_DETECTED"
    exit 1
  fi
fi

OUTPUT_ROOT_SSOT_V1_OK=1
CI_DOCS_WRITE_BLOCK_V1_OK=1
exit 0
