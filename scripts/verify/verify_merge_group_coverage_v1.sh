#!/usr/bin/env bash
set -euo pipefail

MERGE_GROUP_REQUIRED_WORKFLOWS_COVERED_OK=0
trap 'echo "MERGE_GROUP_REQUIRED_WORKFLOWS_COVERED_OK=${MERGE_GROUP_REQUIRED_WORKFLOWS_COVERED_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/REQUIRED_WORKFLOWS_V1.txt"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=REQUIRED_WORKFLOWS_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi

count=0
while IFS= read -r wf; do
  wf="$(printf "%s" "$wf" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [ -z "$wf" ] && continue
  case "$wf" in \#*) continue ;; esac
  count=$((count+1))
done < "$SSOT"

if [ "$count" -lt 1 ]; then
  echo "ERROR_CODE=REQUIRED_WORKFLOWS_SSOT_EMPTY"
  echo "HIT_PATH=$SSOT"
  exit 1
fi

missing=0

while IFS= read -r wf; do
  wf="$(printf "%s" "$wf" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [ -z "$wf" ] && continue
  case "$wf" in \#*) continue ;; esac

  path=".github/workflows/$wf"
  if [ ! -f "$path" ]; then
    echo "ERROR_CODE=REQUIRED_WORKFLOW_FILE_MISSING"
    echo "HIT_PATH=$path"
    missing=1
    continue
  fi

  if ! grep -qE '^[[:space:]]*merge_group[[:space:]]*:' "$path"; then
    echo "ERROR_CODE=MERGE_GROUP_TRIGGER_MISSING"
    echo "HIT_PATH=$path"
    missing=1
  fi
done < "$SSOT"

[ "$missing" -eq 0 ] || exit 1
MERGE_GROUP_REQUIRED_WORKFLOWS_COVERED_OK=1
exit 0
