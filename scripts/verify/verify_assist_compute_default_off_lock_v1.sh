#!/usr/bin/env bash
set -euo pipefail

ASSIST_COMPUTE_POLICY_V1_OK=0
ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1_OK=0

trap 'echo "ASSIST_COMPUTE_POLICY_V1_OK=${ASSIST_COMPUTE_POLICY_V1_OK}";
      echo "ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1_OK=${ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1_OK}"' EXIT

policy="docs/ops/contracts/ASSIST_COMPUTE_POLICY_V1.md"
route="webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/os-llm-gateway.ts"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "ASSIST_COMPUTE_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing token"; exit 1; }
grep -q "DEFAULT_OFF=1" "$policy" || { echo "BLOCK: DEFAULT_OFF missing"; exit 1; }

test -f "$route" || { echo "BLOCK: missing route file"; exit 1; }

# Enforce concrete usage (not comment-only)
# Must include marker + policy path + isAssistEnabled usage in handler
grep -Eq "ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1" "$route" || { echo "BLOCK: missing lock marker"; exit 1; }
grep -Eq "docs/ops/contracts/ASSIST_COMPUTE_POLICY_V1\\.md" "$route" || { echo "BLOCK: route does not reference policy path"; exit 1; }
grep -Eq "ASSIST_COMPUTE_DEFAULT_OFF_GUARD_V1" "$route" || { echo "BLOCK: handler guard not injected"; exit 1; }
grep -Eq "isAssistEnabled\\(req\\)" "$route" || { echo "BLOCK: isAssistEnabled(req) not used"; exit 1; }

ASSIST_COMPUTE_POLICY_V1_OK=1
ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1_OK=1
exit 0
