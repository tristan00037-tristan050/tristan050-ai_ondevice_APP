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

# DoD block marker tokens (verify_repo_contracts.sh cleanup에서 이미 출력)
BEGIN_MARKER='DOD_KV_BLOCK_BEGIN=1'
END_MARKER='DOD_KV_BLOCK_END=1'

# DoD KV must be strictly KEY=0/1
kv_re='^[A-Z0-9_]+=[01]$'

all_ok=1
error_code=""
error_key=""

begin_count=0
end_count=0
in_block=0
saw_any_kv=0

declare -A seen_keys=()

# tmp_out: verify_repo_contracts.sh stdout 캡처 파일
while IFS= read -r line; do
  # 빈 줄은 무시(원문0 유지)
  [[ -z "$line" ]] && continue

  # marker handling
  if [[ "$line" == "$BEGIN_MARKER" ]]; then
    begin_count=$((begin_count+1))
    if [[ $begin_count -gt 1 ]]; then all_ok=0; error_code="BEGIN_DUP"; break; fi
    if [[ $end_count -gt 0 ]]; then all_ok=0; error_code="BEGIN_AFTER_END"; break; fi
    in_block=1
    continue
  fi
  if [[ "$line" == "$END_MARKER" ]]; then
    end_count=$((end_count+1))
    if [[ $begin_count -eq 0 ]]; then all_ok=0; error_code="END_BEFORE_BEGIN"; break; fi
    if [[ $end_count -gt 1 ]]; then all_ok=0; error_code="END_DUP"; break; fi
    in_block=0
    continue
  fi

  # only validate lines inside DoD block
  if [[ $in_block -eq 1 ]]; then
    if [[ ! "$line" =~ $kv_re ]]; then
      all_ok=0; error_code="KV_SHAPE_INVALID"; break
    fi
    saw_any_kv=1

    key="${line%%=*}"
    if [[ -n "${seen_keys[$key]+x}" ]]; then
      all_ok=0; error_code="DUP_KEY"; error_key="$key"; break
    fi
    seen_keys[$key]=1
  fi
done < "$tmp_out"

# post conditions: must have exactly one BEGIN and one END, properly closed, and at least one KV
if [[ $all_ok -eq 1 ]]; then
  if [[ $begin_count -ne 1 || $end_count -ne 1 ]]; then
    all_ok=0; error_code="MARKERS_MISSING"
  elif [[ $in_block -ne 0 ]]; then
    all_ok=0; error_code="BLOCK_NOT_CLOSED"
  elif [[ $saw_any_kv -ne 1 ]]; then
    all_ok=0; error_code="EMPTY_BLOCK"
  fi
fi

if [[ $all_ok -eq 1 ]]; then
  echo "REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=1"
  exit 0
else
  echo "REPO_CONTRACTS_STDOUT_KV_FORMAT_OK=0"
  [[ -n "$error_code" ]] && echo "ERROR_CODE=$error_code"
  [[ -n "$error_key" ]] && echo "ERROR_KEY=$error_key"
  exit 1
fi
