#!/usr/bin/env bash
set -euo pipefail

# P23-P2-06: verify_cyclonedx_ml_bom_v1.sh
# CYCLONEDX_ML_BOM_V1.json 정책 파일 검증.
# packs/*/cyclonedx_bom.json 존재 시 → specVersion=1.6 및 machine-learning-model 타입 검증.
# BOM 파일 없으면 ENFORCE=0 → SKIPPED=1 (pending_real_weights 상태 허용)

CYCLONEDX_ML_BOM_V1_OK=0
trap 'echo "CYCLONEDX_ML_BOM_V1_OK=${CYCLONEDX_ML_BOM_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY_FILE="docs/ops/contracts/CYCLONEDX_ML_BOM_V1.json"
ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$POLICY_FILE" "$ENFORCE" "$ROOT" <<'PYEOF'
import json, sys, os, glob

policy_path, enforce, root = sys.argv[1], sys.argv[2], sys.argv[3]

# --- Policy file validation ---
if not os.path.isfile(policy_path):
    print(f"ERROR_CODE=CYCLONEDX_POLICY_MISSING")
    print(f"HIT_PATH={policy_path}")
    sys.exit(1)

with open(policy_path, encoding='utf-8') as f:
    policy = json.load(f)

required_policy_fields = [
    "schema_version", "policy_id", "cyclonedx_spec_version",
    "required_component_type", "required_fields_per_component"
]
for field in required_policy_fields:
    if field not in policy:
        print(f"ERROR_CODE=POLICY_FIELD_MISSING:{field}")
        sys.exit(1)

if policy["cyclonedx_spec_version"] != "1.6":
    print(f"ERROR_CODE=CYCLONEDX_SPEC_VERSION_WRONG:{policy['cyclonedx_spec_version']}")
    sys.exit(1)

if policy["required_component_type"] != "machine-learning-model":
    print(f"ERROR_CODE=CYCLONEDX_COMPONENT_TYPE_WRONG:{policy['required_component_type']}")
    sys.exit(1)

# --- Check for BOM files ---
bom_files = glob.glob(os.path.join(root, "packs", "*", "cyclonedx_bom.json"))

if not bom_files:
    if enforce == "0":
        print("STATUS=no_bom_files_found")
        print("SKIPPED=1")
        print("NOTE=CycloneDX BOM files not yet generated. Skipping (ENFORCE=0).")
        sys.exit(2)
    else:
        print("ERROR_CODE=CYCLONEDX_BOM_FILES_MISSING_ENFORCE=1")
        sys.exit(1)

# --- Validate each BOM file ---
required_component_fields = policy.get("required_fields_per_component", [])
required_type = policy["required_component_type"]
errors = []

for bom_path in sorted(bom_files):
    with open(bom_path, encoding='utf-8') as f:
        bom = json.load(f)

    spec_version = bom.get("specVersion", "")
    if spec_version != "1.6":
        errors.append(f"SPEC_VERSION_WRONG:{bom_path}:{spec_version}")
        continue

    components = bom.get("components", [])
    if not components:
        errors.append(f"NO_COMPONENTS:{bom_path}")
        continue

    for comp in components:
        if comp.get("type") != required_type:
            errors.append(f"COMPONENT_TYPE_WRONG:{bom_path}:{comp.get('type')}")
        for field in required_component_fields:
            if field not in comp:
                errors.append(f"COMPONENT_FIELD_MISSING:{bom_path}:{field}")

if errors:
    for e in errors:
        print(f"ERROR_CODE={e}")
    sys.exit(1)

print(f"STATUS=ok BOM_FILES={len(bom_files)}")
print("CYCLONEDX_ML_BOM_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "CYCLONEDX_ML_BOM_V1_SKIPPED=1"
  CYCLONEDX_ML_BOM_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

CYCLONEDX_ML_BOM_V1_OK=1
exit 0
