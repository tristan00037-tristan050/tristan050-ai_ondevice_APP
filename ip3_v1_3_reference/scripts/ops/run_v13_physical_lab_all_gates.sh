#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" "$ROOT/tools/windows_real_telemetry_gate.py" "$ROOT" --expected-evidence-class physical_lab --require-battery-present
LINUX_EVIDENCE_CLASS="${LINUX_EVIDENCE_CLASS:-ci_lab}"
DARWIN_EVIDENCE_CLASS="${DARWIN_EVIDENCE_CLASS:-ci_lab}"
"$PYTHON_BIN" "$ROOT/tools/all_platform_telemetry_gate.py" "$ROOT" --require-platforms linux,darwin,windows --expected-evidence-class physical_lab --platform-evidence-class "linux=${LINUX_EVIDENCE_CLASS}" --platform-evidence-class "darwin=${DARWIN_EVIDENCE_CLASS}" --platform-evidence-class windows=physical_lab --strict --require-battery-present
"$PYTHON_BIN" "$ROOT/tools/evidence_taxonomy_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/seal_handoff.py" "$ROOT" --approval-class physical_lab
"$PYTHON_BIN" "$ROOT/tools/claim_guard.py" "$ROOT"
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name "*.pyc" -delete
"$PYTHON_BIN" "$ROOT/tools/clean_package_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/sha256_manifest.py" "$ROOT"
echo "V13_PHYSICAL_LAB_SEALED_HANDOFF_OK"
