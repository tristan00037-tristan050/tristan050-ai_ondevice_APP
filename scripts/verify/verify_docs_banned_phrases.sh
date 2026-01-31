#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# docs/만 스캔(오탐 방지)
# 금지 표현 변형 포함
if rg -n "(원하시면|원하시는|필요하시면|필요하신)" docs ; then
  echo "FAIL: banned phrase found in docs"
  exit 1
fi

echo "DOCS_NO_BANNED_PHRASES_OK=1"
exit 0
