#!/usr/bin/env bash
set -euo pipefail

# P22-AI-07: MODEL_PROVENANCE_IN_TOTO_V1 verifier
MODEL_PROVENANCE_V1_SCHEMA_OK=0
MODEL_PROVENANCE_V1_PACKS_OK=0
trap 'echo "MODEL_PROVENANCE_V1_SCHEMA_OK=${MODEL_PROVENANCE_V1_SCHEMA_OK}"; echo "MODEL_PROVENANCE_V1_PACKS_OK=${MODEL_PROVENANCE_V1_PACKS_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SCHEMA="docs/ops/contracts/MODEL_PROVENANCE_V1.json"
[[ -f "$SCHEMA" ]] || { echo "ERROR_CODE=MODEL_PROVENANCE_SCHEMA_MISSING"; echo "HIT_PATH=$SCHEMA"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

# Validate schema file
"$PYTHON_BIN" - "$SCHEMA" <<'PYEOF'
import json, sys

schema_path = sys.argv[1]
try:
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=MODEL_PROVENANCE_SCHEMA_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

if schema.get("schema_version") != 1:
    print("ERROR_CODE=MODEL_PROVENANCE_SCHEMA_VERSION_INVALID")
    sys.exit(1)

if "schema" not in schema:
    print("ERROR_CODE=MODEL_PROVENANCE_SCHEMA_KEY_MISSING")
    sys.exit(1)

s = schema["schema"]
for key in ["subject", "builder", "build_type", "metadata"]:
    if key not in s:
        print(f"ERROR_CODE=MODEL_PROVENANCE_SCHEMA_FIELD_MISSING")
        print(f"MISSING_FIELD={key}")
        sys.exit(1)

if s.get("builder", {}).get("id") != "ondevice_build_pipeline_v1":
    print("ERROR_CODE=MODEL_PROVENANCE_BUILDER_ID_INVALID")
    sys.exit(1)

if s.get("build_type") != "ondevice_model_pack_v1":
    print("ERROR_CODE=MODEL_PROVENANCE_BUILD_TYPE_INVALID")
    sys.exit(1)

meta = s.get("metadata", {})
for mkey in ["build_started_on", "build_finished_on", "completeness"]:
    if mkey not in meta:
        print(f"ERROR_CODE=MODEL_PROVENANCE_METADATA_FIELD_MISSING")
        print(f"MISSING_FIELD={mkey}")
        sys.exit(1)

required_packs = schema.get("required_packs", [])
if not required_packs:
    print("ERROR_CODE=MODEL_PROVENANCE_REQUIRED_PACKS_MISSING")
    sys.exit(1)
PYEOF

MODEL_PROVENANCE_V1_SCHEMA_OK=1

# Validate each required pack provenance stub
"$PYTHON_BIN" - <<'PYEOF'
import json, sys, os

REQUIRED_PACKS = ["micro_default", "small_default"]
REQUIRED_FIELDS = ["schema_version", "subject", "builder", "build_type", "metadata"]

failed = 0
for pack_id in REQUIRED_PACKS:
    path = f"packs/{pack_id}/provenance.json"
    if not os.path.isfile(path):
        print(f"ERROR_CODE=MODEL_PROVENANCE_PACK_MISSING")
        print(f"HIT_PATH={path}")
        failed = 1
        continue
    try:
        with open(path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR_CODE=MODEL_PROVENANCE_PACK_JSON_INVALID")
        print(f"HIT_PATH={path}")
        failed = 1
        continue
    for field in REQUIRED_FIELDS:
        if field not in doc:
            print(f"ERROR_CODE=MODEL_PROVENANCE_PACK_FIELD_MISSING")
            print(f"PACK={pack_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1
            break
    # Validate subject references correct pack_id
    subjects = doc.get("subject", [])
    if not subjects or subjects[0].get("pack_id") != pack_id:
        print(f"ERROR_CODE=MODEL_PROVENANCE_SUBJECT_PACK_ID_MISMATCH")
        print(f"PACK={pack_id}")
        failed = 1
    # P23-P1-05: slsa_spec_version and in_toto_version required
    if doc.get("slsa_spec_version") != "1.2":
        print(f"ERROR_CODE=MODEL_PROVENANCE_SLSA_VERSION_INVALID")
        print(f"PACK={pack_id}")
        print(f"EXPECTED=1.2")
        print(f"ACTUAL={doc.get('slsa_spec_version')}")
        failed = 1
    if doc.get("in_toto_version") != "v1":
        print(f"ERROR_CODE=MODEL_PROVENANCE_IN_TOTO_VERSION_INVALID")
        print(f"PACK={pack_id}")
        print(f"EXPECTED=v1")
        print(f"ACTUAL={doc.get('in_toto_version')}")
        failed = 1

if failed:
    sys.exit(1)
PYEOF

MODEL_PROVENANCE_V1_PACKS_OK=1
exit 0
