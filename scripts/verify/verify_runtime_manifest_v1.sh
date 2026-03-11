#!/usr/bin/env bash
set -euo pipefail

# P23-P2B-01: verify_runtime_manifest_v1.sh
# packs/*/runtime_manifest.json 존재 및 필수 필드 검증.
# status=pending_real_weights → SKIPPED=1

RUNTIME_MANIFEST_V1_OK=0
trap 'echo "RUNTIME_MANIFEST_V1_OK=${RUNTIME_MANIFEST_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$ENFORCE" <<'PYEOF'
import json, sys, os, glob

enforce = sys.argv[1]

manifest_files = sorted(glob.glob("packs/*/runtime_manifest.json"))

if not manifest_files:
    print("ERROR_CODE=RUNTIME_MANIFEST_NO_FILES_FOUND")
    sys.exit(1)

REQUIRED_FIELDS = [
    "schema_version", "logical_pack_id", "model_format",
    "quantization_mode", "context_length",
    "graph_io_contract", "artifacts", "status"
]
REQUIRED_ARTIFACT_FIELDS = [
    "weights_digest_sha256",
    "tokenizer_digest_sha256",
    "chat_template_digest_sha256",
]
REQUIRED_GRAPH_IO_FIELDS = [
    "input_ids", "attention_mask", "logits"
]

failed = 0
has_pending = False

for path in manifest_files:
    try:
        with open(path, encoding='utf-8') as f:
            m = json.load(f)
    except Exception as e:
        print(f"ERROR_CODE=RUNTIME_MANIFEST_JSON_INVALID HIT_PATH={path}")
        failed = 1
        continue

    for field in REQUIRED_FIELDS:
        if field not in m:
            print(f"ERROR_CODE=RUNTIME_MANIFEST_FIELD_MISSING:{field} HIT_PATH={path}")
            failed = 1

    artifacts = m.get("artifacts", {})
    for field in REQUIRED_ARTIFACT_FIELDS:
        if field not in artifacts:
            print(f"ERROR_CODE=RUNTIME_MANIFEST_ARTIFACT_FIELD_MISSING:{field} HIT_PATH={path}")
            failed = 1

    graph_io = m.get("graph_io_contract", {})
    for field in REQUIRED_GRAPH_IO_FIELDS:
        if field not in graph_io:
            print(f"ERROR_CODE=RUNTIME_MANIFEST_GRAPH_IO_FIELD_MISSING:{field} HIT_PATH={path}")
            failed = 1

    if m.get("status") == "pending_real_weights":
        has_pending = True

if failed:
    sys.exit(1)

if has_pending:
    if enforce == "1":
        print("ERROR_CODE=RUNTIME_MANIFEST_PENDING_ENFORCE=1")
        sys.exit(1)
    else:
        print("STATUS=pending_real_weights")
        print("SKIPPED=1")
        sys.exit(2)

print("STATUS=ok")
print("RUNTIME_MANIFEST_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "RUNTIME_MANIFEST_V1_SKIPPED=1"
  RUNTIME_MANIFEST_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

RUNTIME_MANIFEST_V1_OK=1
exit 0
