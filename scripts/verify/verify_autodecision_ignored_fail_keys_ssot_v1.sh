#!/usr/bin/env bash
# P0-05: Verify AUTODECISION_IGNORED_FAIL_KEYS_V1.txt SSOT hygiene (one key per line, # comments, sorted, no duplicates).
# Meta-only: AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=0|1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SSOT="docs/ops/contracts/AUTODECISION_IGNORED_FAIL_KEYS_V1.txt"
AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=0

if [[ ! -f "$SSOT" ]] || [[ ! -s "$SSOT" ]]; then
  echo "AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=0"
  exit 1
fi

# Extract keys (non-empty, non-comment)
keys=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="${line// /}"
  [[ -z "$line" ]] && continue
  keys+=( "$line" )
done < "$SSOT"

# Check duplicates
seen=""
dup=0
for k in "${keys[@]}"; do
  if [[ "$seen" == *"|${k}|"* ]]; then
    dup=1
    break
  fi
  seen="${seen}|${k}|"
done
if [[ "$dup" -eq 1 ]]; then
  echo "AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=0"
  exit 1
fi

# Check sorted (lexicographic)
sorted=1
n=${#keys[@]}
for (( i=0; i < n - 1; i++ )); do
  j=$(( i + 1 ))
  if [[ "${keys[i]}" > "${keys[j]}" ]]; then
    sorted=0
    break
  fi
done
if [[ "$sorted" -ne 1 ]]; then
  echo "AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=0"
  exit 1
fi

AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=1
echo "AUTODECISION_IGNORED_FAIL_KEYS_SSOT_OK=1"
exit 0
