#!/usr/bin/env bash
set -euo pipefail

RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=0
cleanup(){ echo "RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=${RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK}"; }
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

test -s "scripts/verify/lib/runtime_guard_helpers_v1.sh" || { echo "BLOCK: helper missing"; exit 1; }

# 최소 1개 이상이 helper를 source 해야 함(대표 스크립트 기준)
HIT="$(grep -RIn --exclude-dir=node_modules --exclude='*.md' --exclude='*.txt' --exclude='*.json' \
  "runtime_guard_helpers_v1.sh" scripts/verify 2>/dev/null || true)"

if [[ -z "${HIT}" ]]; then
  echo "BLOCK: no verify script sources runtime_guard_helpers_v1.sh"
  exit 1
fi

RUNTIME_GUARD_HELPERS_V1_ADOPTED_OK=1
exit 0

