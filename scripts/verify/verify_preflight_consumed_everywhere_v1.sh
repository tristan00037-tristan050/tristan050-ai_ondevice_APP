#!/usr/bin/env bash
set -euo pipefail

PREFLIGHT_ACTION_CONSUMED_BY_REQUIRED_WORKFLOWS_OK=0
PREFLIGHT_DUPLICATE_PREP_PATH_0_OK=0

trap 'echo "PREFLIGHT_ACTION_CONSUMED_BY_REQUIRED_WORKFLOWS_OK=$PREFLIGHT_ACTION_CONSUMED_BY_REQUIRED_WORKFLOWS_OK";
      echo "PREFLIGHT_DUPLICATE_PREP_PATH_0_OK=$PREFLIGHT_DUPLICATE_PREP_PATH_0_OK"' EXIT

policy="docs/ops/contracts/PREFLIGHT_CONSUMPTION_POLICY_V1.md"
ssot="docs/ops/contracts/REQUIRED_WORKFLOWS_V1.txt"

test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "PREFLIGHT_CONSUMPTION_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing token"; exit 1; }

test -f "$ssot" || { echo "BLOCK: missing $ssot"; exit 1; }
test -s "$ssot" || { echo "BLOCK: empty $ssot"; exit 1; }

missing=0
dup=0

# "중복 prep 경로"로 간주할 강한 시그널들:
# - .build_stamp.json 직접 생성/언급
# - bff-accounting: workflow에서 직접 deps 설치 및 build (preflight 단일 소스 위반)
dup_re='(\.build_stamp\.json|Create build stamp|Build bff-accounting|packages/bff-accounting|/bff-accounting/dist)'

while IFS= read -r wf || [ -n "$wf" ]; do
  wf="${wf%%#*}"
  wf="$(echo "$wf" | awk '{$1=$1;print}')"
  [ -z "$wf" ] && continue

  f=".github/workflows/$wf"
  test -f "$f" || { echo "BLOCK: required workflow missing: $f"; exit 1; }

  # 1) preflight 소비 강제
  grep -q "uses: ./.github/actions/preflight_v1" "$f" || {
    echo "BLOCK: $wf does not consume preflight_v1 action"
    missing=1
  }

  # 2) 중복 prep 경로 차단
  if grep -Eq "$dup_re" "$f"; then
    echo "BLOCK: $wf contains duplicate prep path signals (manual build/stamp)"
    dup=1
  fi
done < "$ssot"

[ "$missing" -eq 0 ] || exit 1
[ "$dup" -eq 0 ] || exit 1

PREFLIGHT_ACTION_CONSUMED_BY_REQUIRED_WORKFLOWS_OK=1
PREFLIGHT_DUPLICATE_PREP_PATH_0_OK=1
exit 0
