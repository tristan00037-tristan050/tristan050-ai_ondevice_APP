#!/usr/bin/env bash
set -euo pipefail

SSOT_REGISTRY_COVERAGE_OK=0
SSOT_REGISTRY_STUB_COUNT=0
finish() {
  echo "SSOT_REGISTRY_COVERAGE_OK=${SSOT_REGISTRY_COVERAGE_OK}"
  echo "SSOT_REGISTRY_STUB_COUNT=${SSOT_REGISTRY_STUB_COUNT}"
}
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REGISTRY="docs/ops/contracts/SSOT_REGISTRY_V1.txt"
test -f "$REGISTRY" || { echo "ERROR_CODE=SSOT_REGISTRY_MISSING_OR_INVALID"; exit 1; }
grep -q '^SSOT_REGISTRY_V1_TOKEN=1' "$REGISTRY" || { echo "ERROR_CODE=SSOT_REGISTRY_MISSING_OR_INVALID"; exit 1; }

# SSOT files: docs/ops/contracts/ under .txt .md .json, exclude registry itself
ssot_list=$(find docs/ops/contracts -maxdepth 1 -type f \( -name '*.txt' -o -name '*.md' -o -name '*.json' \) ! -name 'SSOT_REGISTRY_V1.txt' | sort)

# 1) Every SSOT must have at least one SSOT=<path> CONSUMER= or SSOT=<path> STATUS=stub
while IFS= read -r ssot; do
  [ -z "$ssot" ] && continue
  if grep -qE "^SSOT=${ssot}[[:space:]]+CONSUMER=" "$REGISTRY" 2>/dev/null; then
    continue
  fi
  if grep -qE "^SSOT=${ssot}[[:space:]]+STATUS=stub" "$REGISTRY" 2>/dev/null; then
    continue
  fi
  echo "ERROR_CODE=SSOT_REGISTRY_MISSING_ENTRY"
  echo "HIT_SSOT=${ssot}"
  exit 1
done <<< "$ssot_list"

# 2) Every CONSUMER in registry must exist as a file (STATUS=stub lines have no CONSUMER)
stub_count=0
while IFS= read -r line; do
  if [[ "$line" =~ ^SSOT=[^[:space:]]+[[:space:]]+STATUS=stub ]]; then
    ((stub_count++)) || true
    continue
  fi
  [[ "$line" =~ ^SSOT=[^[:space:]]+[[:space:]]+CONSUMER=(.+)$ ]] || continue
  con="${BASH_REMATCH[1]}"
  con="${con%"${con##*[![:space:]]}"}"
  [ -z "$con" ] && continue
  if [ ! -f "$con" ]; then
    echo "ERROR_CODE=SSOT_REGISTRY_CONSUMER_NOT_FOUND"
    echo "HIT_CONSUMER=${con}"
    exit 1
  fi
done < <(grep -E '^SSOT=[^[:space:]]+[[:space:]]+(CONSUMER=|STATUS=stub)' "$REGISTRY" 2>/dev/null)

SSOT_REGISTRY_STUB_COUNT=$stub_count
SSOT_REGISTRY_COVERAGE_OK=1
exit 0
