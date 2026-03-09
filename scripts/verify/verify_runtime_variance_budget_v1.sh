#!/usr/bin/env bash
set -euo pipefail

# P22-AI-10: RUNTIME_VARIANCE_BUDGET_V1 verifier
# Cross-validates RUNTIME_VARIANCE_BUDGET_V1.json latency_p95_max_ms against
# MODEL_PACK_CATALOG_V1.json latency_budget_ms_p95 for each pack.
RUNTIME_VARIANCE_BUDGET_V1_OK=0
trap 'echo "RUNTIME_VARIANCE_BUDGET_V1_OK=${RUNTIME_VARIANCE_BUDGET_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BUDGET="docs/ops/contracts/RUNTIME_VARIANCE_BUDGET_V1.json"
CATALOG="docs/ops/contracts/MODEL_PACK_CATALOG_V1.json"

[[ -f "$BUDGET" ]] || { echo "ERROR_CODE=RUNTIME_VARIANCE_BUDGET_MISSING"; echo "HIT_PATH=$BUDGET"; exit 1; }
[[ -f "$CATALOG" ]] || { echo "ERROR_CODE=MODEL_PACK_CATALOG_MISSING"; echo "HIT_PATH=$CATALOG"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$BUDGET" "$CATALOG" <<'PYEOF'
import json, sys

budget_path, catalog_path = sys.argv[1], sys.argv[2]

try:
    with open(budget_path, 'r', encoding='utf-8') as f:
        budget = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=RUNTIME_VARIANCE_BUDGET_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

try:
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=MODEL_PACK_CATALOG_JSON_INVALID")
    print(f"DETAIL={e}")
    sys.exit(1)

# Validate budget schema
if budget.get("schema_version") != 1:
    print("ERROR_CODE=RUNTIME_VARIANCE_BUDGET_SCHEMA_VERSION_INVALID")
    sys.exit(1)

budgets = budget.get("budgets", [])
if not isinstance(budgets, list) or len(budgets) == 0:
    print("ERROR_CODE=RUNTIME_VARIANCE_BUDGET_ENTRIES_MISSING")
    sys.exit(1)

REQUIRED_BUDGET_FIELDS = [
    "pack_id", "latency_p95_max_ms", "latency_variance_max_ms",
    "cpu_time_max_ms", "memory_rss_max_mb",
]

# Build catalog index: pack_id → latency_budget_ms_p95
catalog_packs = {p["pack_id"]: p for p in catalog.get("packs", [])}

failed = 0
for entry in budgets:
    pack_id = entry.get("pack_id", "")
    for field in REQUIRED_BUDGET_FIELDS:
        if field not in entry:
            print(f"ERROR_CODE=RUNTIME_VARIANCE_BUDGET_FIELD_MISSING")
            print(f"PACK={pack_id}")
            print(f"MISSING_FIELD={field}")
            failed = 1
            break

    # Cross-validate: latency_p95_max_ms must match catalog latency_budget_ms_p95
    if pack_id in catalog_packs:
        catalog_p95 = catalog_packs[pack_id].get("latency_budget_ms_p95")
        budget_p95 = entry.get("latency_p95_max_ms")
        if catalog_p95 != budget_p95:
            print(f"ERROR_CODE=RUNTIME_VARIANCE_LATENCY_P95_MISMATCH")
            print(f"PACK={pack_id}")
            print(f"CATALOG_VALUE={catalog_p95}")
            print(f"BUDGET_VALUE={budget_p95}")
            failed = 1
    else:
        print(f"ERROR_CODE=RUNTIME_VARIANCE_PACK_NOT_IN_CATALOG")
        print(f"PACK={pack_id}")
        failed = 1

if failed:
    sys.exit(1)
PYEOF

RUNTIME_VARIANCE_BUDGET_V1_OK=1
exit 0
