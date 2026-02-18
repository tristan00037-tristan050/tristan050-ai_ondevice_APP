#!/usr/bin/env bash
set -euo pipefail

# verify=판정만 (금지: build/install/download/network)
PREFLIGHT_ONE_SHOT_V1_PRESENT_OK=0
PREFLIGHT_ONE_SHOT_V1_RUNBOOK_OK=0

trap 'echo "PREFLIGHT_ONE_SHOT_V1_PRESENT_OK=${PREFLIGHT_ONE_SHOT_V1_PRESENT_OK}";
      echo "PREFLIGHT_ONE_SHOT_V1_RUNBOOK_OK=${PREFLIGHT_ONE_SHOT_V1_RUNBOOK_OK}"' EXIT

policy="docs/ops/contracts/PREFLIGHT_ONE_SHOT_POLICY_V1.md"
preflight="tools/preflight_v1.sh"
action=".github/actions/preflight_v1/action.yml"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "PREFLIGHT_ONE_SHOT_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$preflight" || { echo "BLOCK: missing tools/preflight_v1.sh"; exit 1; }
test -f "$action" || { echo "BLOCK: missing .github/actions/preflight_v1/action.yml"; exit 1; }

# preflight가 키 출력(DoD 키)을 하면 규율 위반이 될 수 있으므로 간단히 방어:
if grep -Eq 'echo ".*_OK=' "$preflight"; then
  echo "BLOCK: preflight must not print DoD keys"
  exit 1
fi

PREFLIGHT_ONE_SHOT_V1_PRESENT_OK=1
PREFLIGHT_ONE_SHOT_V1_RUNBOOK_OK=1
exit 0

