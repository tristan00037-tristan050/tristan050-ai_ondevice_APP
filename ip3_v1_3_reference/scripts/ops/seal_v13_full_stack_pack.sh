#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
OUT="${2:-/mnt/data/Butler_IP3_OnDevice_Context_Routing_Engine_v1_3_FULL_STACK_WORLD_CLASS_SEALABLE_DEV_PACK.zip}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$ROOT"
bash scripts/ops/run_v13_full_stack_local_gates.sh .
find . -name '__pycache__' -type d -prune -exec rm -rf {} +
find . -name '*.pyc' -delete
cd "$(dirname "$ROOT")"
BASE="$(basename "$ROOT")"
rm -f "$OUT"
zip -qr "$OUT" "$BASE" -x "*/.git/*" "*/__pycache__/*" "*.pyc" "*/.DS_Store" "*/._*" "*.zip"
shasum -a 256 "$OUT" > "$OUT.sha256"
echo "V13_FULL_STACK_PACK_SEALED $OUT"
