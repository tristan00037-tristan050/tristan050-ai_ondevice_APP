#!/usr/bin/env bash
set -euo pipefail

# P23-P2-05: verify_replayable_proof_bundle_v1.sh
# REPLAYABLE_PROOF_BUNDLE_V1.json 존재, 필드, bundle_digest 검증.
# status=pending_real_weights → ENFORCE=0 → SKIPPED=1

REPLAYABLE_PROOF_BUNDLE_V1_OK=0
trap 'echo "REPLAYABLE_PROOF_BUNDLE_V1_OK=${REPLAYABLE_PROOF_BUNDLE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BUNDLE_FILE="docs/ops/contracts/REPLAYABLE_PROOF_BUNDLE_V1.json"
ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$BUNDLE_FILE" "$ENFORCE" <<'PYEOF'
import json, sys, os, hashlib

bundle_path, enforce = sys.argv[1], sys.argv[2]

if not os.path.isfile(bundle_path):
    print(f"ERROR_CODE=REPLAYABLE_PROOF_BUNDLE_MISSING")
    print(f"HIT_PATH={bundle_path}")
    sys.exit(1)

with open(bundle_path, encoding='utf-8') as f:
    bundle = json.load(f)

required_fields = [
    "schema_version", "bundle_id", "components",
    "merkle_root_digest", "bundle_digest_sha256", "status"
]
for field in required_fields:
    if field not in bundle:
        print(f"ERROR_CODE=BUNDLE_FIELD_MISSING:{field}")
        sys.exit(1)

status = bundle.get("status", "")
bundle_digest = bundle.get("bundle_digest_sha256", "")
merkle_root = bundle.get("merkle_root_digest", "")

is_placeholder = (
    status in ("pending_real_weights", "PLACEHOLDER") or
    bundle_digest == "PLACEHOLDER" or
    merkle_root == "REQUIRED"
)

if is_placeholder:
    if enforce == "0":
        print("STATUS=pending")
        print("SKIPPED=1")
        sys.exit(2)
    else:
        print("ERROR_CODE=REPLAYABLE_PROOF_BUNDLE_PENDING_ENFORCE=1")
        sys.exit(1)

# Validate components
components = bundle.get("components", {})
if not components:
    print("ERROR_CODE=REPLAYABLE_PROOF_BUNDLE_EMPTY_COMPONENTS")
    sys.exit(1)

for comp_id, comp in components.items():
    for f in ["source", "digest_sha256"]:
        if f not in comp:
            print(f"ERROR_CODE=COMPONENT_FIELD_MISSING:{f} in {comp_id}")
            sys.exit(1)
    if comp["digest_sha256"] in ("REQUIRED", "PLACEHOLDER", ""):
        print(f"ERROR_CODE=COMPONENT_DIGEST_PLACEHOLDER:{comp_id}")
        sys.exit(1)
    if len(comp["digest_sha256"]) != 64:
        print(f"ERROR_CODE=COMPONENT_DIGEST_INVALID:{comp_id}")
        sys.exit(1)

# Validate merkle_root length
if len(merkle_root) != 64:
    print(f"ERROR_CODE=MERKLE_ROOT_INVALID_LENGTH")
    sys.exit(1)

# Validate bundle_digest_sha256 self-check
bundle_without_digest = {k: v for k, v in bundle.items() if k != "bundle_digest_sha256"}
canonical = json.dumps(bundle_without_digest, sort_keys=True, ensure_ascii=False)
expected_digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
if bundle_digest != expected_digest:
    print(f"ERROR_CODE=BUNDLE_DIGEST_MISMATCH")
    print(f"EXPECTED={expected_digest}")
    print(f"ACTUAL={bundle_digest}")
    sys.exit(1)

print("STATUS=ok")
print("REPLAYABLE_PROOF_BUNDLE_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "REPLAYABLE_PROOF_BUNDLE_V1_SKIPPED=1"
  REPLAYABLE_PROOF_BUNDLE_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

REPLAYABLE_PROOF_BUNDLE_V1_OK=1
exit 0
