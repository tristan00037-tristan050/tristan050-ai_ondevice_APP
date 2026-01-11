#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "FAIL: not a git repo" >&2; exit 2; }
TARGET="${ROOT}/.github/workflows"
test -d "$TARGET" || { echo "FAIL: missing .github/workflows" >&2; exit 2; }

BAD="$(rg -n --no-heading '^\s*(bash|sh)\s+scripts/ops/verify_' "$TARGET" || true)"
if [ -n "$BAD" ]; then
  echo "FAIL: direct verify_* calls found in workflows (run_gate only)"
  echo "$BAD"
  exit 1
fi
echo "PASS: no direct verify_* calls in workflows"
