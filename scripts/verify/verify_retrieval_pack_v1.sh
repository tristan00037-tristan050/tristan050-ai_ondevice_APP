#!/usr/bin/env bash
set -euo pipefail

# P22-AI-05: ONDEVICE_RETRIEVAL_PACK_V1 verifier
RETRIEVAL_PACK_V1_OK=0
trap 'echo "RETRIEVAL_PACK_V1_OK=${RETRIEVAL_PACK_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MANIFEST="packs/retrieval_default/manifest.json"
[[ -f "$MANIFEST" ]] || { echo "ERROR_CODE=RETRIEVAL_PACK_MANIFEST_MISSING"; echo "HIT_PATH=$MANIFEST"; exit 1; }

POLICY_TS="tools/retrieval/retrieval_policy_v1.ts"
[[ -f "$POLICY_TS" ]] || { echo "ERROR_CODE=RETRIEVAL_POLICY_MISSING"; echo "HIT_PATH=$POLICY_TS"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

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

# trust_level must be "untrusted-input" for supply chain registration
if manifest.get("trust_level") != "untrusted-input":
    print("ERROR_CODE=RETRIEVAL_PACK_TRUST_LEVEL_INVALID")
    print(f"EXPECTED=untrusted-input")
    print(f"ACTUAL={manifest.get('trust_level')}")
    sys.exit(1)

if not manifest.get("supply_chain_registered"):
    print("ERROR_CODE=RETRIEVAL_PACK_SUPPLY_CHAIN_NOT_REGISTERED")
    sys.exit(1)
PYEOF

RETRIEVAL_PACK_V1_OK=1
exit 0
