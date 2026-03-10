#!/usr/bin/env bash
set -euo pipefail

# AI-P3-03: ENTERPRISE_ROUTER_ENFORCEMENT_V1 verifier
ENTERPRISE_PACK_ELIGIBILITY_V1_OK=0
ROUTER_POLICY_DIGEST_MATCH_OK=0
ROUTER_ROLLOUT_RING_ENFORCED_OK=0
trap '
  echo "ENTERPRISE_PACK_ELIGIBILITY_V1_OK=${ENTERPRISE_PACK_ELIGIBILITY_V1_OK}"
  echo "ROUTER_POLICY_DIGEST_MATCH_OK=${ROUTER_POLICY_DIGEST_MATCH_OK}"
  echo "ROUTER_ROLLOUT_RING_ENFORCED_OK=${ROUTER_ROLLOUT_RING_ENFORCED_OK}"
' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

ROUTER_TS="tools/routing/model_router_v1.ts"
POLICY_TS="tools/enterprise/pack_assignment_policy_v1.ts"

[[ -f "$ROUTER_TS" ]] || { echo "ERROR_CODE=ROUTER_TS_MISSING"; echo "HIT_PATH=$ROUTER_TS"; exit 1; }
[[ -f "$POLICY_TS" ]] || { echo "ERROR_CODE=POLICY_TS_MISSING"; echo "HIT_PATH=$POLICY_TS"; exit 1; }

echo "=== ENTERPRISE_ROUTER_ENFORCEMENT_V1 ==="

# 1. isPackEnterpriseEligible 존재 확인
if ! grep -q "isPackEnterpriseEligible" "$ROUTER_TS"; then
  echo "FAILED_GUARD=ENTERPRISE_PACK_ELIGIBILITY_FN_MISSING"
  exit 1
fi

# 2. policy_digest 매칭 로직 존재 확인
if ! grep -q "policy_digest" "$ROUTER_TS"; then
  echo "FAILED_GUARD=ROUTER_POLICY_DIGEST_CHECK_MISSING"
  exit 1
fi

# 3. rollout_ring 매칭 로직 존재 확인
if ! grep -q "rollout_ring" "$ROUTER_TS"; then
  echo "FAILED_GUARD=ROUTER_ROLLOUT_RING_CHECK_MISSING"
  exit 1
fi

# 4. NO_ELIGIBLE_PACK throw 존재 확인
if ! grep -q "NO_ELIGIBLE_PACK" "$ROUTER_TS"; then
  echo "FAILED_GUARD=ROUTER_NO_ELIGIBLE_PACK_THROW_MISSING"
  exit 1
fi

# 5. computeUtility 존재 확인
if ! grep -q "computeUtility" "$ROUTER_TS"; then
  echo "FAILED_GUARD=ROUTER_COMPUTE_UTILITY_MISSING"
  exit 1
fi

# 6. COMPUTED_AT_BUILD_TIME 차단 로직 존재 확인 (pack_assignment_policy_v1.ts)
if ! grep -q "COMPUTED_AT_BUILD_TIME" "$POLICY_TS"; then
  echo "FAILED_GUARD=POLICY_DIGEST_UNRESOLVED_BLOCK_MISSING"
  exit 1
fi

ENTERPRISE_PACK_ELIGIBILITY_V1_OK=1
ROUTER_POLICY_DIGEST_MATCH_OK=1
ROUTER_ROLLOUT_RING_ENFORCED_OK=1
echo "ENTERPRISE_PACK_ELIGIBILITY_V1_OK=1"
echo "ROUTER_POLICY_DIGEST_MATCH_OK=1"
echo "ROUTER_ROLLOUT_RING_ENFORCED_OK=1"
exit 0
