#!/usr/bin/env bash
set -euo pipefail

REQUIRED_WORKFLOWS_LIST_V1_OK=0
WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=0
trap 'echo "REQUIRED_WORKFLOWS_LIST_V1_OK=$REQUIRED_WORKFLOWS_LIST_V1_OK"; echo "WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=$WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK"' EXIT

f="docs/ops/contracts/REQUIRED_WORKFLOWS_LIST_V1.txt"
[ -f "$f" ] || { echo "BLOCK: missing $f"; exit 1; }
grep -q "REQUIRED_WORKFLOWS_LIST_V1_TOKEN=1" "$f" || { echo "BLOCK: token missing"; exit 1; }
REQUIRED_WORKFLOWS_LIST_V1_OK=1

# 각 워크플로 파일에서 on: merge_group 존재 확인 (fail-closed)
while IFS= read -r line; do
  wf="$(echo "$line" | sed 's/^WORKFLOW=//')"
  file=".github/workflows/${wf}.yml"
  [ -f "$file" ] || { echo "BLOCK: missing workflow file $file"; exit 1; }
  grep -q "merge_group" "$file" || { echo "BLOCK: merge_group missing in $file"; exit 1; }
done < <(grep '^WORKFLOW=' "$f")

WORKFLOW_MERGE_GROUP_COVERAGE_V1_OK=1
exit 0

