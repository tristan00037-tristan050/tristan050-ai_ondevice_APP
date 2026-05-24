#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" "$ROOT/tools/run_unit_tests.py"
"$PYTHON_BIN" "$ROOT/tools/windows_real_telemetry_gate.py" "$ROOT" --expected-evidence-class ci_lab
"$PYTHON_BIN" "$ROOT/tools/all_platform_telemetry_gate.py" "$ROOT" --require-platforms linux,darwin,windows --expected-evidence-class ci_lab --strict
"$PYTHON_BIN" "$ROOT/tools/evidence_taxonomy_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/seal_handoff.py" "$ROOT" --approval-class ci_lab
"$PYTHON_BIN" "$ROOT/tools/claim_guard.py" "$ROOT"
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name "*.pyc" -delete
"$PYTHON_BIN" "$ROOT/tools/clean_package_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/sha256_manifest.py" "$ROOT"
echo "V13_CI_LAB_SEALED_HANDOFF_OK"
