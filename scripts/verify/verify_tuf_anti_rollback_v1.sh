#!/usr/bin/env bash
set -euo pipefail

# P23-P2-02: verify_tuf_anti_rollback_v1.sh
# TUF_ANTI_ROLLBACK_V1.json 존재 및 필드 검증.
# rollback_protection=true, freeze_attack_protection=true 필수.
# ENFORCE=0 → 정책 파일 없으면 SKIPPED=1

TUF_ANTI_ROLLBACK_V1_OK=0
trap 'echo "TUF_ANTI_ROLLBACK_V1_OK=${TUF_ANTI_ROLLBACK_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY_FILE="docs/ops/contracts/TUF_ANTI_ROLLBACK_V1.json"
TS_FILE="tools/supply-chain/tuf_policy_v1.ts"

ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$POLICY_FILE" "$TS_FILE" "$ENFORCE" <<'PYEOF'
import json, sys, os

policy_path, ts_path, enforce = sys.argv[1], sys.argv[2], sys.argv[3]

if not os.path.isfile(policy_path):
    if enforce == "0":
        print("STATUS=policy_missing")
        print("SKIPPED=1")
        sys.exit(2)
    print(f"ERROR_CODE=TUF_ANTI_ROLLBACK_POLICY_MISSING")
    print(f"HIT_PATH={policy_path}")
    sys.exit(1)

with open(policy_path, encoding='utf-8') as f:
    policy = json.load(f)

required_fields = [
    "schema_version", "policy_id", "rollback_protection",
    "freeze_attack_protection", "metadata_expiry_hours_max",
    "root_rotation_required_on_compromise", "consistent_snapshots"
]
for field in required_fields:
    if field not in policy:
        print(f"ERROR_CODE=TUF_POLICY_FIELD_MISSING:{field}")
        sys.exit(1)

if policy["rollback_protection"] is not True:
    print("ERROR_CODE=TUF_ROLLBACK_PROTECTION_NOT_TRUE")
    sys.exit(1)

if policy["freeze_attack_protection"] is not True:
    print("ERROR_CODE=TUF_FREEZE_ATTACK_PROTECTION_NOT_TRUE")
    sys.exit(1)

# TypeScript symbol checks
if not os.path.isfile(ts_path):
    print(f"ERROR_CODE=TUF_TS_MISSING")
    print(f"HIT_PATH={ts_path}")
    sys.exit(1)

ts_src = open(ts_path, encoding='utf-8').read()
required_symbols = [
    "verifyTufMetadata",
    "buildTufPolicyDigest",
    "TufAntiRollbackPolicy",
    "TufVerifyResult",
    "ROLLBACK_DETECTED",
    "FREEZE_ATTACK_DETECTED",
    "TUF_METADATA_EXPIRY_EXCEEDS_POLICY_MAX",
    "metadata_expiry_hours_max",
]
for sym in required_symbols:
    if sym not in ts_src:
        print(f"ERROR_CODE=TUF_TS_SYMBOL_MISSING:{sym}")
        sys.exit(1)

print("STATUS=ok")
print("TUF_ANTI_ROLLBACK_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "TUF_ANTI_ROLLBACK_V1_SKIPPED=1"
  TUF_ANTI_ROLLBACK_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

TUF_ANTI_ROLLBACK_V1_OK=1
exit 0
