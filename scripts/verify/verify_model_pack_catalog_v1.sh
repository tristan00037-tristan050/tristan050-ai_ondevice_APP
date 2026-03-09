#!/usr/bin/env bash
set -euo pipefail

# P22-AI-01: MODEL_PACK_CATALOG_V1 verifier
MODEL_PACK_CATALOG_V1_SCHEMA_OK=0
MODEL_PACK_CATALOG_V1_PACKS_OK=0
trap 'echo "MODEL_PACK_CATALOG_V1_SCHEMA_OK=${MODEL_PACK_CATALOG_V1_SCHEMA_OK}"; echo "MODEL_PACK_CATALOG_V1_PACKS_OK=${MODEL_PACK_CATALOG_V1_PACKS_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CATALOG="docs/ops/contracts/MODEL_PACK_CATALOG_V1.json"
GUIDE="docs/ops/contracts/MODEL_PACK_CATALOG_GUIDE.md"

[[ -f "$CATALOG" ]] || { echo "ERROR_CODE=MODEL_PACK_CATALOG_MISSING"; echo "HIT_PATH=$CATALOG"; exit 1; }
[[ -f "$GUIDE" ]] || { echo "ERROR_CODE=MODEL_PACK_CATALOG_GUIDE_MISSING"; echo "HIT_PATH=$GUIDE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$CATALOG" <<'PYEOF'
import json, sys

catalog_path = sys.argv[1]

try:
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=MODEL_PACK_CATALOG_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

# Schema check
if catalog.get("schema_version") != 1:
    print("ERROR_CODE=MODEL_PACK_CATALOG_SCHEMA_VERSION_INVALID")
    sys.exit(1)

if not isinstance(catalog.get("packs"), list) or len(catalog["packs"]) == 0:
    print("ERROR_CODE=MODEL_PACK_CATALOG_PACKS_MISSING")
    sys.exit(1)

print("MODEL_PACK_CATALOG_V1_SCHEMA_OK=1")

# Packs check
REQUIRED_FIELDS = [
    "pack_id", "tier", "quant", "runtime_id",
    "weights_digest_sha256", "tokenizer_digest_sha256", "config_digest_sha256",
    "min_ram_mb", "latency_budget_ms_p95",
]
REQUIRED_PACK_IDS = {"micro_default", "small_default"}

pack_ids = set()
for pack in catalog["packs"]:
    pid = pack.get("pack_id", "")
    for field in REQUIRED_FIELDS:
        if field not in pack:
            print(f"ERROR_CODE=MODEL_PACK_CATALOG_FIELD_MISSING")
            print(f"PACK={pid}")
            print(f"MISSING_FIELD={field}")
            sys.exit(1)
    pack_ids.add(pid)

missing = REQUIRED_PACK_IDS - pack_ids
if missing:
    print(f"ERROR_CODE=MODEL_PACK_CATALOG_REQUIRED_PACK_MISSING")
    print(f"MISSING_PACKS={','.join(sorted(missing))}")
    sys.exit(1)

print("MODEL_PACK_CATALOG_V1_PACKS_OK=1")
PYEOF

MODEL_PACK_CATALOG_V1_SCHEMA_OK=1
MODEL_PACK_CATALOG_V1_PACKS_OK=1
exit 0
