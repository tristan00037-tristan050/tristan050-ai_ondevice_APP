#!/usr/bin/env bash
set -euo pipefail

# AI-P3-04: POLICY_CONFLICT_ENGINE_V1 verifier
POLICY_CONFLICT_ENGINE_V1_OK=0
trap 'echo "POLICY_CONFLICT_ENGINE_V1_OK=${POLICY_CONFLICT_ENGINE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TS_FILE="tools/enterprise/enterprise_scope_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=ENTERPRISE_SCOPE_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

echo "=== POLICY_CONFLICT_ENGINE_V1 ==="

# 1. resolveEffectivePolicy 존재 확인
if ! grep -q "resolveEffectivePolicy" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_CONFLICT_ENGINE_MISSING"
  exit 1
fi

# 2. PRIVILEGE_ESCALATION 차단 로직 존재 확인
if ! grep -q "POLICY_PRIVILEGE_ESCALATION" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_ESCALATION_CHECK_MISSING"
  exit 1
fi

# 3. PACK_ESCALATION 차단 로직 존재 확인
if ! grep -q "POLICY_PACK_ESCALATION" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_PACK_CHECK_MISSING"
  exit 1
fi

# 4. DATA_TIER_ESCALATION 차단 로직 존재 확인
if ! grep -q "POLICY_DATA_TIER_ESCALATION" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_DATA_TIER_CHECK_MISSING"
  exit 1
fi

# 5. dataTierRank 3개 값 존재 확인 (public:0, restricted:2)
if ! grep -q "public.*0" "$TS_FILE" || ! grep -q "restricted.*2" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_DATA_TIER_RANK_MISSING"
  exit 1
fi

# 6. assertNoPolicyConflicts 존재 확인
if ! grep -q "assertNoPolicyConflicts" "$TS_FILE"; then
  echo "FAILED_GUARD=POLICY_NO_CONFLICT_ASSERT_MISSING"
  exit 1
fi

# 7. ScopedPolicy + PolicyConflict 인터페이스 존재 확인
if ! grep -q "ScopedPolicy" "$TS_FILE"; then
  echo "FAILED_GUARD=SCOPED_POLICY_INTERFACE_MISSING"
  exit 1
fi

POLICY_CONFLICT_ENGINE_V1_OK=1
echo "POLICY_CONFLICT_ENGINE_V1_OK=1"
exit 0
