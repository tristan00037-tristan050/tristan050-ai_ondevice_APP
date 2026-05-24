#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
OUT_DIR="${2:-/tmp}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" "$ROOT/tools/clean_package_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/claim_guard.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/sha256_manifest.py" "$ROOT"
BASE="Butler_IP3_OnDevice_Context_Routing_Engine_v1_3_CI_LAB_Windows_Telemetry_Strict_Gate_SEALABLE"
mkdir -p "$OUT_DIR"
( cd "$(dirname "$ROOT")" && zip -qr "$OUT_DIR/$BASE.zip" "$(basename "$ROOT")" -x '*/__pycache__/*' '*.pyc' '*/.DS_Store' '*/._*' )
shasum -a 256 "$OUT_DIR/$BASE.zip" > "$OUT_DIR/$BASE.zip.sha256"
echo "V13_CI_LAB_PACKAGED $OUT_DIR/$BASE.zip"
