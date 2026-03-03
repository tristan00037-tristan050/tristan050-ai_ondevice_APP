#!/usr/bin/env bash
set -euo pipefail

BUILD_PROVENANCE_ATTEST_V1_OK=0
finish() { [ "${BUILD_PROVENANCE_ATTEST_V1_OK:-0}" -eq 1 ] && echo "BUILD_PROVENANCE_ATTEST_V1_OK=1"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/BUILD_PROVENANCE_ATTEST_SSOT_V1.txt"

if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"
  exit 1
fi
grep -q '^BUILD_PROVENANCE_ATTEST_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

WORKFLOW=$(grep -E '^WORKFLOW=' "$SSOT" | head -n1 | cut -d= -f2- | tr -d '\r')
[ -n "$WORKFLOW" ] || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

if [ ! -f "$WORKFLOW" ]; then
  echo "ERROR_CODE=WORKFLOW_NOT_FOUND"
  exit 1
fi

# permissions: id-token: write (somewhere in workflow)
grep -qE 'id-token:\s*write|id-token: *write' "$WORKFLOW" || { echo "ERROR_CODE=ID_TOKEN_PERMISSION_MISSING"; exit 1; }

# attest step/action keyword (REQUIRE_ATTEST_STEP_KEYWORD and REQUIRE_ATTEST_ACTION_KEYWORD)
grep -qi 'attest' "$WORKFLOW" || { echo "ERROR_CODE=ATTEST_STEP_MISSING"; exit 1; }
grep -q 'attest-build-provenance' "$WORKFLOW" || { echo "ERROR_CODE=ATTEST_STEP_MISSING"; exit 1; }

BUILD_PROVENANCE_ATTEST_V1_OK=1
exit 0
