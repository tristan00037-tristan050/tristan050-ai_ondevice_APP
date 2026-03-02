#!/usr/bin/env bash
set -euo pipefail

AGENTS_MD_PRESENT_OK=0
AGENTS_MD_HASH_PRESENT_OK=0

finish() {
  echo "AGENTS_MD_PRESENT_OK=${AGENTS_MD_PRESENT_OK}"
  echo "AGENTS_MD_HASH_PRESENT_OK=${AGENTS_MD_HASH_PRESENT_OK}"
}
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

test -f AGENTS.md || { echo "ERROR_CODE=AGENTS_MD_MISSING"; exit 1; }
AGENTS_MD_PRESENT_OK=1

# meta-only: 원문 출력 금지, sha256만 출력
if command -v shasum >/dev/null 2>&1; then
  sha="$(shasum -a 256 AGENTS.md | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  sha="$(sha256sum AGENTS.md | awk '{print $1}')"
else
  echo "ERROR_CODE=SHA256_TOOL_MISSING"
  exit 1
fi

[ -n "$sha" ] || { echo "ERROR_CODE=SHA256_EMPTY"; exit 1; }
echo "AGENTS_MD_SHA256=${sha}"
AGENTS_MD_HASH_PRESENT_OK=1
exit 0
