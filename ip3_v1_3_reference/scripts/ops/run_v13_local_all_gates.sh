#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" "$ROOT/tools/run_unit_tests.py"
"$PYTHON_BIN" "$ROOT/tools/evidence_taxonomy_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/claim_guard.py" "$ROOT"
if "$PYTHON_BIN" "$ROOT/tools/all_platform_telemetry_gate.py" "$ROOT" --require-platforms linux,darwin,windows --expected-evidence-class ci_lab --strict; then
  echo "LOCAL_FAIL_CLOSED_EXPECTATION_FAIL all-platform CI unexpectedly passed in local packaging"
  exit 2
else
  echo "ALL_PLATFORM_TELEMETRY_FAIL_CLOSED_OK local_package_has_no_external_ci_evidence"
fi
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name "*.pyc" -delete
"$PYTHON_BIN" "$ROOT/tools/clean_package_gate.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/sha256_manifest.py" "$ROOT"
"$PYTHON_BIN" "$ROOT/tools/claim_guard.py" "$ROOT"
echo "V13_LOCAL_SEALABLE_CANDIDATE_GATE_OK"
