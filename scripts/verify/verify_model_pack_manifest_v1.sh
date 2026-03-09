#!/usr/bin/env bash
set -euo pipefail

# P22-AI-02 / P23-P0B-01: ONDEVICE_REAL_MODEL_PACK_V1 verifier (3-layer structure)
MODEL_PACK_MANIFEST_V1_OK=0
trap 'echo "MODEL_PACK_MANIFEST_V1_OK=${MODEL_PACK_MANIFEST_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

REQUIRED_CONFIG_FIELDS="pack_id model_type vocab_size hidden_size num_layers num_heads max_seq_len quant"
PACK_IDS="micro_default small_default"

REQUIRED_LOGICAL_FIELDS="pack_id status weights_digest_sha256 tokenizer_digest_sha256 normalizer_digest_sha256 pretokenizer_digest_sha256 postprocessor_digest_sha256 chat_template_digest_sha256 config_digest_sha256 special_token_map_digest_sha256"
REQUIRED_COMPILED_FIELDS="compiled_pack_id backend_id delegate_id precision_mode compiled_artifact_digest_sha256 reduced_op_config_digest_sha256 compile_flags_digest_sha256"
REQUIRED_QUALITY_FIELDS="quality_fingerprint_sha256 context_budget_tokens ttft_ms_p95_budget decode_tps_floor thermal_degradation_pct_10min_max"

failed=0
for pack_id in $PACK_IDS; do
  manifest="packs/${pack_id}/manifest.json"
  config_file="packs/${pack_id}/config.json"

  [[ -f "$manifest" ]] || { echo "ERROR_CODE=PACK_MANIFEST_MISSING"; echo "HIT_PATH=$manifest"; failed=1; continue; }
  [[ -f "$config_file" ]] || { echo "ERROR_CODE=PACK_CONFIG_MISSING"; echo "HIT_PATH=$config_file"; failed=1; continue; }

  "$PYTHON_BIN" - "$manifest" "$config_file" "$pack_id" \
    "$REQUIRED_LOGICAL_FIELDS" "$REQUIRED_COMPILED_FIELDS" "$REQUIRED_QUALITY_FIELDS" "$REQUIRED_CONFIG_FIELDS" <<'PYEOF'
import json, sys

manifest_path, config_path, pack_id = sys.argv[1], sys.argv[2], sys.argv[3]
logical_fields_str, compiled_fields_str, quality_fields_str, config_fields_str = sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]

try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        doc = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=PACK_MANIFEST_JSON_INVALID")
    print(f"HIT_PATH={manifest_path}")
    print(f"DETAIL={e}")
    sys.exit(1)

# Verify 3-layer structure keys present
for layer_key in ("logical_model_pack", "compiled_runtime_pack", "quality_contract"):
    if layer_key not in doc:
        print(f"ERROR_CODE=PACK_MANIFEST_LAYER_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_LAYER={layer_key}")
        sys.exit(1)

# Verify logical_model_pack fields
logical = doc["logical_model_pack"]
for field in logical_fields_str.split():
    if field not in logical:
        print(f"ERROR_CODE=PACK_MANIFEST_LOGICAL_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

if logical.get("pack_id") != pack_id:
    print(f"ERROR_CODE=PACK_MANIFEST_PACK_ID_MISMATCH")
    print(f"EXPECTED={pack_id}")
    print(f"ACTUAL={logical.get('pack_id')}")
    sys.exit(1)

# Verify compiled_runtime_pack fields
compiled = doc["compiled_runtime_pack"]
for field in compiled_fields_str.split():
    if field not in compiled:
        print(f"ERROR_CODE=PACK_MANIFEST_COMPILED_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# Verify quality_contract fields
quality = doc["quality_contract"]
for field in quality_fields_str.split():
    if field not in quality:
        print(f"ERROR_CODE=PACK_MANIFEST_QUALITY_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

# Verify config.json
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
except Exception as e:
    print(f"ERROR_CODE=PACK_CONFIG_JSON_INVALID")
    print(f"HIT_PATH={config_path}")
    print(f"DETAIL={e}")
    sys.exit(1)

for field in config_fields_str.split():
    if field not in config:
        print(f"ERROR_CODE=PACK_CONFIG_FIELD_MISSING")
        print(f"PACK={pack_id}")
        print(f"MISSING_FIELD={field}")
        sys.exit(1)

if config.get("pack_id") != pack_id:
    print(f"ERROR_CODE=PACK_CONFIG_PACK_ID_MISMATCH")
    print(f"EXPECTED={pack_id}")
    print(f"ACTUAL={config.get('pack_id')}")
    sys.exit(1)
PYEOF
  rc=$?
  [[ $rc -eq 0 ]] || { failed=1; }
done

[[ "$failed" -eq 0 ]] || exit 1

MODEL_PACK_MANIFEST_V1_OK=1
exit 0
