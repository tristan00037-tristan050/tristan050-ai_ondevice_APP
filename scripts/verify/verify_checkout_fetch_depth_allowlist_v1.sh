#!/usr/bin/env bash
set -euo pipefail

CHECKOUT_FETCH_DEPTH_ALLOWLIST_V1_OK=0
trap 'echo "CHECKOUT_FETCH_DEPTH_ALLOWLIST_V1_OK=${CHECKOUT_FETCH_DEPTH_ALLOWLIST_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/REQUIRED_FULL_HISTORY_WORKFLOWS_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=FULL_HISTORY_SSOT_MISSING"; echo "HIT_PATH=$SSOT"; exit 1; }
grep -q '^REQUIRED_FULL_HISTORY_WORKFLOWS_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=FULL_HISTORY_TOKEN_MISSING"; exit 1; }

# Every workflow listed in SSOT must have fetch-depth: 0
missing=0
while IFS= read -r wf; do
  wf="${wf%%#*}"
  wf="${wf#"${wf%%[![:space:]]*}"}"
  wf="${wf%"${wf##*[![:space:]]}"}"
  [[ -z "$wf" ]] && continue
  [[ "$wf" =~ ^[A-Z0-9_]+=.*$ ]] && continue  # skip token lines

  path=".github/workflows/$wf"
  if [[ ! -f "$ROOT/$path" ]]; then
    echo "ERROR_CODE=FULL_HISTORY_WORKFLOW_MISSING"
    echo "HIT_PATH=$path"
    missing=1
    continue
  fi

  if ! grep -qE 'fetch-depth[[:space:]]*:[[:space:]]*0' "$ROOT/$path"; then
    echo "ERROR_CODE=FULL_HISTORY_FETCH_DEPTH_MISSING"
    echo "HIT_PATH=$path"
    missing=1
  fi
done < "$SSOT"

[[ "$missing" -eq 0 ]] || exit 1
CHECKOUT_FETCH_DEPTH_ALLOWLIST_V1_OK=1
exit 0
