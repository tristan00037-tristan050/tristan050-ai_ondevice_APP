#!/bin/bash
# verify_no_unconditional_ok.sh
# Guard: Fail if unconditional OK=1 patterns found in test source files

set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel)"
cd "${TOPLEVEL}"

# Find test files
TEST_FILES=$(find webcore_appcore_starter_4_17/backend/control_plane/tests -type f -name "*.ts" 2>/dev/null || true)

if [ -z "${TEST_FILES}" ]; then
  echo "INFO: No test files found"
  exit 0
fi

# Check for unconditional OK=1 patterns
# Pattern: console.log('*_OK=1') or similar without conditional check
VIOLATIONS=0

while IFS= read -r file; do
  # Check for unconditional OK=1 prints (not inside if/else blocks)
  # This is a heuristic: look for console.log with OK=1 that's not preceded by conditional logic
  if grep -n "console\.log.*OK=1" "${file}" > /dev/null 2>&1; then
    # Check if it's inside a conditional block (if/else/ternary)
    # Simple check: if line has OK=1 and no if/else/ternary on nearby lines, it's likely unconditional
    if ! grep -B5 "console\.log.*OK=1" "${file}" | grep -qE "(if|else|ternary|\?|:)" 2>/dev/null; then
      echo "ERROR: Unconditional OK=1 found in ${file}"
      grep -n "console\.log.*OK=1" "${file}" || true
      VIOLATIONS=$((VIOLATIONS + 1))
    fi
  fi
done <<< "${TEST_FILES}"

if [ "${VIOLATIONS}" -gt 0 ]; then
  echo "FAIL: Found ${VIOLATIONS} unconditional OK=1 pattern(s) in test files"
  echo "OK keys must only be emitted by verification scripts, not test source files"
  exit 1
fi

echo "PASS: No unconditional OK=1 patterns found in test files"
exit 0

