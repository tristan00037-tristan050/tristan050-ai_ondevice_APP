#!/usr/bin/env bash
set -euo pipefail

# P22-AI-08 / P23-P1-05: MODEL_PACK_SBOM_EXT_V1 verifier (SPDX-2.3 + documentDescribes)
MODEL_PACK_SBOM_V1_OK=0
trap 'echo "MODEL_PACK_SBOM_V1_OK=${MODEL_PACK_SBOM_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

PACK_IDS="micro_default small_default"
REQUIRED_FIELDS="spdxVersion dataLicense SPDXID name documentNamespace documentDescribes packages"

failed=0
for pack_id in $PACK_IDS; do
  sbom="packs/${pack_id}/sbom.json"
  [[ -f "$sbom" ]] || { echo "ERROR_CODE=PACK_SBOM_MISSING"; echo "HIT_PATH=$sbom"; failed=1; continue; }

  "$PYTHON_BIN" - "$sbom" "$pack_id" "$REQUIRED_FIELDS" <<'PYEOF'
import json, sys

sbom_path, pack_id, required_fields_str = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    with open(sbom_path, 'r', encoding='utf-8') as f:
        doc = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=PACK_SBOM_JSON_INVALID")
    print(f"HIT_PATH={sbom_path}")
    print(f"DETAIL={e}")
    sys.exit(1)

# Check required top-level fields
for field in required_fields_str.split():
    if field not in doc:
        print(f"ERROR_CODE=PACK_SBOM_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# spdxVersion must be SPDX-2.x
spdx_ver = doc.get("spdxVersion", "")
if not spdx_ver.startswith("SPDX-2."):
    print(f"ERROR_CODE=PACK_SBOM_SPDX_VERSION_INVALID")
    print(f"PACK={pack_id}")
    print(f"ACTUAL={spdx_ver}")
    sys.exit(1)

# documentDescribes must be a non-empty list
describes = doc.get("documentDescribes", [])
if not isinstance(describes, list) or len(describes) == 0:
    print(f"ERROR_CODE=PACK_SBOM_DOCUMENT_DESCRIBES_EMPTY")
    print(f"PACK={pack_id}")
    sys.exit(1)

# packages must have at least 1 entry
packages = doc.get("packages", [])
if not isinstance(packages, list) or len(packages) == 0:
    print(f"ERROR_CODE=PACK_SBOM_PACKAGES_EMPTY")
    print(f"PACK={pack_id}")
    sys.exit(1)

# First package must have required SPDX fields
pkg = packages[0]
for pkg_field in ["SPDXID", "name", "downloadLocation", "licenseConcluded", "licenseDeclared", "copyrightText"]:
    if pkg_field not in pkg:
        print(f"ERROR_CODE=PACK_SBOM_PKG_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={pkg_field}")
        sys.exit(1)

if pkg.get("name") != pack_id:
    print(f"ERROR_CODE=PACK_SBOM_PKG_NAME_MISMATCH")
    print(f"PACK={pack_id}")
    print(f"ACTUAL={pkg.get('name')}")
    sys.exit(1)
PYEOF
  rc=$?
  [[ $rc -eq 0 ]] || { failed=1; }
done

[[ "$failed" -eq 0 ]] || exit 1

MODEL_PACK_SBOM_V1_OK=1
exit 0
