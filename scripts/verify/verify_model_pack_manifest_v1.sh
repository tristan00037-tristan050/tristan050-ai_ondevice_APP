#!/usr/bin/env bash
set -euo pipefail

# P22-AI-02: ONDEVICE_REAL_MODEL_PACK_V1 verifier
MODEL_PACK_MANIFEST_V1_OK=0
trap 'echo "MODEL_PACK_MANIFEST_V1_OK=${MODEL_PACK_MANIFEST_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

REQUIRED_MANIFEST_FIELDS="pack_id tier quant runtime_id weights_digest_sha256 tokenizer_digest_sha256 config_digest_sha256 min_ram_mb latency_budget_ms_p95"
REQUIRED_CONFIG_FIELDS="pack_id model_type vocab_size hidden_size num_layers num_heads max_seq_len quant"
PACK_IDS="micro_default small_default"

failed=0
for pack_id in $PACK_IDS; do
  manifest="packs/${pack_id}/manifest.json"
  config_file="packs/${pack_id}/config.json"

  [[ -f "$manifest" ]] || { echo "ERROR_CODE=PACK_MANIFEST_MISSING"; echo "HIT_PATH=$manifest"; failed=1; continue; }
  [[ -f "$config_file" ]] || { echo "ERROR_CODE=PACK_CONFIG_MISSING"; echo "HIT_PATH=$config_file"; failed=1; continue; }

  "$PYTHON_BIN" - "$manifest" "$config_file" "$pack_id" "$REQUIRED_MANIFEST_FIELDS" "$REQUIRED_CONFIG_FIELDS" <<'PYEOF'
import json, sys

manifest_path, config_path, pack_id, manifest_fields_str, config_fields_str = sys.argv[1:6]

def check_json(path, required_fields_str, label):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR_CODE={label}_JSON_INVALID")
        print(f"HIT_PATH={path}")
        print(f"DETAIL={e}")
        sys.exit(1)
    for field in required_fields_str.split():
        if field not in doc:
            print(f"ERROR_CODE={label}_FIELD_MISSING")
            print(f"PACK={pack_id}")
            print(f"MISSING_FIELD={field}")
            sys.exit(1)
    pid = doc.get("pack_id", "")
    if pid != pack_id:
        print(f"ERROR_CODE={label}_PACK_ID_MISMATCH")
        print(f"EXPECTED={pack_id}")
        print(f"ACTUAL={pid}")
        sys.exit(1)

check_json(manifest_path, manifest_fields_str, "PACK_MANIFEST")
check_json(config_path, config_fields_str, "PACK_CONFIG")
PYEOF
  rc=$?
  [[ $rc -eq 0 ]] || { failed=1; }
done

[[ "$failed" -eq 0 ]] || exit 1

MODEL_PACK_MANIFEST_V1_OK=1
exit 0
