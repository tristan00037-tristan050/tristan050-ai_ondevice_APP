#!/usr/bin/env bash
set -euo pipefail

# grep/rg 공용 검색기(설치 금지: rg 없으면 grep로 폴백)
scan() {
  if command -v rg >/dev/null 2>&1; then
    rg "$@"
  else
    local pat="" path="."
    for a in "$@"; do
      case "$a" in -*) ;; *) if [ -z "$pat" ]; then pat="$a"; else path="$a"; fi ;; esac
    done
    [ -n "$pat" ] || return 1
    grep -RIn -- "$pat" "$path"
  fi
}

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# docs/만 스캔(오탐 방지)
# 금지 표현 변형 포함
if scan -n "(원하시면|원하시는|필요하시면|필요하신)" docs ; then
  echo "FAIL: banned phrase found in docs"
  exit 1
fi

echo "DOCS_NO_BANNED_PHRASES_OK=1"
exit 0
