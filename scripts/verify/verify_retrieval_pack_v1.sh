#!/usr/bin/env bash
set -euo pipefail

# P22-AI-05 / P23-P1-04: ONDEVICE_RETRIEVAL_PACK_V1 + RETRIEVAL_EVIDENCE_PACK_V2 verifier
RETRIEVAL_PACK_V1_OK=0
trap 'echo "RETRIEVAL_PACK_V1_OK=${RETRIEVAL_PACK_V1_OK}"' EXIT

ENFORCE="${RETRIEVAL_EVIDENCE_V2_ENFORCE:-0}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MANIFEST="packs/retrieval_default/manifest.json"
[[ -f "$MANIFEST" ]] || { echo "ERROR_CODE=RETRIEVAL_PACK_MANIFEST_MISSING"; echo "HIT_PATH=$MANIFEST"; exit 1; }

POLICY_TS="tools/retrieval/retrieval_policy_v1.ts"
[[ -f "$POLICY_TS" ]] || { echo "ERROR_CODE=RETRIEVAL_POLICY_MISSING"; echo "HIT_PATH=$POLICY_TS"; exit 1; }

V2_POLICY="docs/ops/contracts/RETRIEVAL_EVIDENCE_PACK_V2_POLICY.json"
[[ -f "$V2_POLICY" ]] || { echo "ERROR_CODE=RETRIEVAL_EVIDENCE_V2_POLICY_MISSING"; echo "HIT_PATH=$V2_POLICY"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

# V1 base checks
"$PYTHON_BIN" - "$MANIFEST" <<'PYEOF'
import json, sys

manifest_path = sys.argv[1]

try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=RETRIEVAL_PACK_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

REQUIRED_FIELDS = [
    "pack_id", "pack_type", "version", "runtime_id",
    "index_digest_sha256", "config_digest_sha256",
    "status", "trust_level",
]
for field in REQUIRED_FIELDS:
    if field not in manifest:
        print(f"ERROR_CODE=RETRIEVAL_PACK_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

if manifest.get("pack_id") != "retrieval_default":
    print("ERROR_CODE=RETRIEVAL_PACK_ID_MISMATCH")
    print(f"ACTUAL={manifest.get('pack_id')}")
    sys.exit(1)

if manifest.get("pack_type") != "retrieval":
    print("ERROR_CODE=RETRIEVAL_PACK_TYPE_INVALID")
    print(f"ACTUAL={manifest.get('pack_type')}")
    sys.exit(1)

if manifest.get("trust_level") != "untrusted-input":
    print("ERROR_CODE=RETRIEVAL_PACK_TRUST_LEVEL_INVALID")
    print(f"EXPECTED=untrusted-input")
    print(f"ACTUAL={manifest.get('trust_level')}")
    sys.exit(1)

if not manifest.get("supply_chain_registered"):
    print("ERROR_CODE=RETRIEVAL_PACK_SUPPLY_CHAIN_NOT_REGISTERED")
    sys.exit(1)
PYEOF

# V2 evidence pack checks (ENFORCE=0 → SKIPPED on placeholder values)
set +e
"$PYTHON_BIN" - "$MANIFEST" "$V2_POLICY" "$ENFORCE" <<'PYEOF'
import json, sys

manifest_path, policy_path, enforce = sys.argv[1], sys.argv[2], sys.argv[3]

with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

with open(policy_path, 'r', encoding='utf-8') as f:
    policy = json.load(f)

V2_REQUIRED = policy.get("required_fields", [])
PLACEHOLDER = "REQUIRED"

failed = 0
has_placeholder = False

for field in V2_REQUIRED:
    if field not in manifest:
        print(f"ERROR_CODE=RETRIEVAL_EVIDENCE_V2_FIELD_MISSING")
        print(f"MISSING_FIELD={field}")
        failed = 1
    elif manifest[field] == PLACEHOLDER:
        has_placeholder = True

if failed:
    sys.exit(1)

# log_policy must be digest_only
expected_log = policy.get("log_policy", "digest_only")
if manifest.get("log_policy") != expected_log:
    print(f"ERROR_CODE=RETRIEVAL_EVIDENCE_LOG_POLICY_INVALID")
    print(f"EXPECTED={expected_log}")
    print(f"ACTUAL={manifest.get('log_policy')}")
    sys.exit(1)

# trust_tier must be untrusted-input
expected_tier = policy.get("trust_tier_default", "untrusted-input")
if manifest.get("trust_tier") != expected_tier:
    print(f"ERROR_CODE=RETRIEVAL_EVIDENCE_TRUST_TIER_INVALID")
    print(f"EXPECTED={expected_tier}")
    print(f"ACTUAL={manifest.get('trust_tier')}")
    sys.exit(1)

if has_placeholder:
    if enforce == "1":
        print("ERROR_CODE=RETRIEVAL_EVIDENCE_V2_PLACEHOLDER_BLOCKED")
        print("NOTE=Real retrieval digests required before release")
        sys.exit(1)
    else:
        sys.exit(2)  # skip
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "RETRIEVAL_EVIDENCE_V2_SKIPPED=1"
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

RETRIEVAL_PACK_V1_OK=1
exit 0
