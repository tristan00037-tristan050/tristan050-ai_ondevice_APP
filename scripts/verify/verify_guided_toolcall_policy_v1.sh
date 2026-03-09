#!/usr/bin/env bash
set -euo pipefail

# P23-P1-03: GUIDED_TOOLCALL_POLICY_V1 verifier
GUIDED_TOOLCALL_POLICY_V1_OK=0
trap 'echo "GUIDED_TOOLCALL_POLICY_V1_OK=${GUIDED_TOOLCALL_POLICY_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/GUIDED_TOOLCALL_POLICY_V1.json"
[[ -f "$POLICY" ]] || { echo "ERROR_CODE=GUIDED_TOOLCALL_POLICY_MISSING"; echo "HIT_PATH=$POLICY"; exit 1; }

TS_FILE="tools/toolcall/toolcall_schema_v1.ts"
[[ -f "$TS_FILE" ]] || { echo "ERROR_CODE=TOOLCALL_SCHEMA_TS_MISSING"; echo "HIT_PATH=$TS_FILE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$POLICY" <<'PYEOF'
import json, sys

policy_path = sys.argv[1]

try:
    with open(policy_path, 'r', encoding='utf-8') as f:
        policy = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=GUIDED_TOOLCALL_POLICY_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

REQUIRED_FIELDS = [
    "schema_version", "policy_id",
    "required_digests_per_action_pack",
    "unconstrained_json_tool_call_allowed"
]
for field in REQUIRED_FIELDS:
    if field not in policy:
        print(f"ERROR_CODE=GUIDED_TOOLCALL_POLICY_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# unconstrained_json_tool_call_allowed MUST be false
if policy.get("unconstrained_json_tool_call_allowed") is not False:
    print("ERROR_CODE=GUIDED_TOOLCALL_UNCONSTRAINED_NOT_BLOCKED")
    print(f"ACTUAL={policy.get('unconstrained_json_tool_call_allowed')}")
    sys.exit(1)

# required_digests_per_action_pack must include the 3 required digest fields
required_digests = policy.get("required_digests_per_action_pack", [])
EXPECTED = {"tool_schema_digest_sha256", "guided_generation_schema_digest_sha256", "tool_policy_digest_sha256"}
missing = EXPECTED - set(required_digests)
if missing:
    print(f"ERROR_CODE=GUIDED_TOOLCALL_REQUIRED_DIGESTS_MISSING")
    print(f"MISSING={sorted(missing)}")
    sys.exit(1)
PYEOF

# Verify TypeScript symbols exist
failed=0
for symbol in "ToolSchema" "GuidedToolCallContract" \
              "buildToolSchemaDigest" "assertGuidedToolCallContract"; do
  if ! grep -q "$symbol" "$TS_FILE"; then
    echo "ERROR_CODE=TOOLCALL_SCHEMA_TS_SYMBOL_MISSING"
    echo "MISSING_SYMBOL=${symbol}"
    failed=1
  fi
done

[[ "$failed" -eq 0 ]] || exit 1

GUIDED_TOOLCALL_POLICY_V1_OK=1
exit 0
