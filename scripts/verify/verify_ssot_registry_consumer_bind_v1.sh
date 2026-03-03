#!/usr/bin/env bash
set -euo pipefail

SSOT_REGISTRY_CONSUMER_BIND_OK=0
finish() { echo "SSOT_REGISTRY_CONSUMER_BIND_OK=${SSOT_REGISTRY_CONSUMER_BIND_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REGISTRY="docs/ops/contracts/SSOT_REGISTRY_V1.txt"
BASE_REF="${SSOT_REGISTRY_BASE_REF:-origin/main}"
git rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || { echo "ERROR_CODE=BASE_REF_UNAVAILABLE"; exit 1; }

get_consumers_for_ssot() {
  local ssot="$1"
  grep -E "^SSOT=${ssot}[[:space:]]+CONSUMER=" "$REGISTRY" 2>/dev/null | sed -E 's/.*CONSUMER=//' | tr -d '\r' || true
}

check_bind() {
  local changed_ssot="$1"
  local changed_files="$2"
  local ssot
  while IFS= read -r ssot; do
    [ -z "$ssot" ] && continue
    consumers=$(get_consumers_for_ssot "$ssot")
    [ -z "$consumers" ] && continue
    found=0
    while IFS= read -r con; do
      [ -z "$con" ] && continue
      if echo "$changed_files" | grep -qFx "$con"; then found=1; break; fi
    done <<< "$consumers"
    if [ "$found" -eq 0 ]; then
      first_con=$(echo "$consumers" | head -n1)
      echo "ERROR_CODE=SSOT_CHANGED_WITHOUT_BOUND_CONSUMER_CHANGE"
      echo "HIT_SSOT=${ssot}"
      echo "HIT_REQUIRED_CONSUMER=${first_con}"
      return 1
    fi
  done <<< "$changed_ssot"
  return 0
}

ssot_c=$(git diff --name-only "$BASE_REF"...HEAD -- "docs/ops/contracts/" 2>/dev/null | grep -E '\.(txt|md|json)$' || true)
files_c=$(git diff --name-only "$BASE_REF"...HEAD 2>/dev/null || true)
ssot_u=$(git diff --name-only HEAD -- "docs/ops/contracts/" 2>/dev/null | grep -E '\.(txt|md|json)$' || true)
files_u=$(git diff --name-only HEAD 2>/dev/null || true)

if [ -z "$ssot_c" ] && [ -z "$ssot_u" ]; then
  SSOT_REGISTRY_CONSUMER_BIND_OK=1
  exit 0
fi

[ -n "$ssot_c" ] && { check_bind "$ssot_c" "$files_c" || exit 1; }
[ -n "$ssot_u" ] && { check_bind "$ssot_u" "$files_u" || exit 1; }

SSOT_REGISTRY_CONSUMER_BIND_OK=1
exit 0
