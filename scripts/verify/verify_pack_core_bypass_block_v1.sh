#!/usr/bin/env bash
set -euo pipefail

PACK_CORE_BYPASS_POLICY_V1_OK=0
PACK_FORBIDDEN_IMPORT_BLOCK_V1_OK=0
PACK_MANIFEST_SCHEMA_LOCK_V1_OK=0

trap 'echo "PACK_CORE_BYPASS_POLICY_V1_OK=${PACK_CORE_BYPASS_POLICY_V1_OK}";
      echo "PACK_FORBIDDEN_IMPORT_BLOCK_V1_OK=${PACK_FORBIDDEN_IMPORT_BLOCK_V1_OK}";
      echo "PACK_MANIFEST_SCHEMA_LOCK_V1_OK=${PACK_MANIFEST_SCHEMA_LOCK_V1_OK}"' EXIT

policy="docs/ops/contracts/PACK_CORE_BYPASS_POLICY_V1.md"
test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "PACK_CORE_BYPASS_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

# Pack root: use model_packs if packs/ does not exist (probe result)
if [ -d "packs" ]; then
  PACK_ROOT="packs"
elif [ -d "model_packs" ]; then
  PACK_ROOT="model_packs"
else
  echo "BLOCK: missing pack root dir (packs or model_packs)"
  exit 1
fi

# Forbidden imports from pack code
FORBIDDEN_RE='(from|require\().*(policy/|router/|egress/|ops_hub/|ops-hub/|trace/|export/)'

# scan only code-like files
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if grep -EIn "^[[:space:]]*[^#/].*$FORBIDDEN_RE" "$f" >/dev/null 2>&1; then
    echo "BLOCK: forbidden core import in pack: $f"
    exit 1
  fi
done < <(find "$PACK_ROOT" -type f \( -name "*.js" -o -name "*.cjs" -o -name "*.mjs" -o -name "*.ts" \) 2>/dev/null || true)

# Manifest forbidden fields (routing_override/egress_mode/record_mode etc.)
if find "$PACK_ROOT" -type f \( -name "*manifest*.json" -o -name "*manifest*.yml" -o -name "*manifest*.yaml" \) 2>/dev/null | grep -q .; then
  if grep -RInE '"(routing_override|egress_mode|record_mode|routingOverride|egressMode|recordMode)"[[:space:]]*:' "$PACK_ROOT" >/dev/null 2>&1; then
    echo "BLOCK: forbidden manifest override field present"
    exit 1
  fi
fi

PACK_CORE_BYPASS_POLICY_V1_OK=1
PACK_FORBIDDEN_IMPORT_BLOCK_V1_OK=1
PACK_MANIFEST_SCHEMA_LOCK_V1_OK=1
exit 0
