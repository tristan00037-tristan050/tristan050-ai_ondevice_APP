#!/usr/bin/env bash
# P0-04: Verify verify_repo_contracts.sh stdout KEY=VALUE contract. DoD block only (between DOD_KV_BLOCK_BEGIN/END).
# Meta-only: REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=0|1. Exit 0 when block present and all lines match KEY=VALUE.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=0

tmp_out="$(mktemp)"
trap 'rm -f "$tmp_out"' EXIT

# Run producer; capture stdout (and stderr so we see guard output). We only validate the captured stdout.
bash scripts/verify/verify_repo_contracts.sh >"$tmp_out" 2>&1 || true

# Extract only between DOD_KV_BLOCK_BEGIN=1 and DOD_KV_BLOCK_END=1 (inclusive lines optional; we take inner lines)
block=""
in_block=0
while IFS= read -r line; do
  if [[ "$line" =~ ^DOD_KV_BLOCK_BEGIN=1 ]]; then
    in_block=1
    continue
  fi
  if [[ "$line" =~ ^DOD_KV_BLOCK_END=1 ]]; then
    in_block=0
    continue
  fi
  [[ "$in_block" -eq 1 ]] && block="${block}${line}"$'\n'
done < "$tmp_out"

# Contract: block non-empty and every line matches KEY=VALUE (key: uppercase/numbers/underscore, value: rest)
if [[ -z "${block//[$'\n']/}" ]]; then
  echo "REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=0"
  exit 1
fi

kv_re='^[A-Z0-9_]+=.*$'
all_ok=1
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ ! "$line" =~ $kv_re ]]; then
    all_ok=0
    break
  fi
done <<< "$block"

if [[ "$all_ok" -eq 1 ]]; then
  REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=1
fi

echo "REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=${REPO_CONTRACTS_STDOUT_KV_FORMAT_OK}"
[[ "$REPO_CONTRACTS_STDOUT_KV_FORMAT_OK" -eq 1 ]] && exit 0
exit 1
