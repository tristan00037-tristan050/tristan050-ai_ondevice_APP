#!/usr/bin/env bash
# P0-03: Verify autodecision keys SSOT hygiene (required + ignored-fail). Inline # strip + trim, format ^[A-Z0-9_]+$, dup/sort fail-closed.
# Meta-only output.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

AUTODECISION_KEYS_SSOT_HYGIENE_OK=0

check_one_ssot() {
  local ssot="$1"
  local keys=()
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    if [[ ! "$line" =~ ^[A-Z0-9_]+$ ]]; then
      return 1
    fi
    keys+=( "$line" )
  done < "$ssot"
  # Duplicates
  local seen=""
  for k in "${keys[@]}"; do
    if [[ "$seen" == *"|${k}|"* ]]; then
      return 1
    fi
    seen="${seen}|${k}|"
  done
  # Sorted
  local n=${#keys[@]}
  for (( i=0; i < n - 1; i++ )); do
    j=$(( i + 1 ))
    if [[ "${keys[i]}" > "${keys[j]}" ]]; then
      return 1
    fi
  done
  return 0
}

REQUIRED_SSOT="docs/ops/contracts/AUTODECISION_REQUIRED_KEYS_V1.txt"
IGNORED_SSOT="docs/ops/contracts/AUTODECISION_IGNORED_FAIL_KEYS_V1.txt"

if [[ ! -f "$REQUIRED_SSOT" ]] || [[ ! -s "$REQUIRED_SSOT" ]]; then
  echo "AUTODECISION_KEYS_SSOT_HYGIENE_OK=0"
  exit 1
fi
if [[ ! -f "$IGNORED_SSOT" ]] || [[ ! -s "$IGNORED_SSOT" ]]; then
  echo "AUTODECISION_KEYS_SSOT_HYGIENE_OK=0"
  exit 1
fi

if ! check_one_ssot "$REQUIRED_SSOT"; then
  echo "AUTODECISION_KEYS_SSOT_HYGIENE_OK=0"
  exit 1
fi
if ! check_one_ssot "$IGNORED_SSOT"; then
  echo "AUTODECISION_KEYS_SSOT_HYGIENE_OK=0"
  exit 1
fi

AUTODECISION_KEYS_SSOT_HYGIENE_OK=1
echo "AUTODECISION_KEYS_SSOT_HYGIENE_OK=1"
exit 0
