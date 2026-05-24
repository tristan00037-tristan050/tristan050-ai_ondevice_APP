#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$ROOT"
"$PYTHON_BIN" tools/run_full_stack_local_gates.py .
