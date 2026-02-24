#!/usr/bin/env bash
# POLICY_HEADERS_SCHEMA_V1 (PR-P0-BFF-01): Load policy YAMLs via bff-accounting loader; fail-closed on schema/YAML/file.
# Meta-only output only. No policy content/raw logs (원문0).
# Requires: npm run build:packages:server in webcore_appcore_starter_4_17 (dist) before running.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

ENTRYPOINT="webcore_appcore_starter_4_17/packages/bff-accounting/dist/policy/loader.js"
echo "ENTRYPOINT=${ENTRYPOINT}"

LOADER_DIST="webcore_appcore_starter_4_17/packages/bff-accounting/dist/policy/loader.js"
if [[ ! -f "$LOADER_DIST" ]]; then
  echo "POLICY_HEADERS_SCHEMA_V1_OK=0"
  echo "ERROR_CODE=FILE_NOT_FOUND"
  echo "INDEX="
  echo "FILEPATH=${REPO_ROOT}/${LOADER_DIST}"
  exit 1
fi

stderr_file="$(mktemp)"
trap 'rm -f "$stderr_file"' EXIT

if node scripts/verify/run_policy_headers_schema_check.mjs 2>"$stderr_file"; then
  # Node script already printed POLICY_HEADERS_SCHEMA_V1_OK=1 and POLICY_HEADERS_RULE_DESCRIPTION_PRESENT_OK=1 to stdout
  exit 0
fi

# Failure: meta-only from loader stderr (no raw dump)
ERROR_CODE=""
FILEPATH=""
INDEX=""
if grep -q "Schema validation failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="$(grep -o "error_code: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/error_code: '\(.*\)'/\1/" || true)"
  FILEPATH="$(grep -o "filepath: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/filepath: '\(.*\)'/\1/" || true)"
  if [[ -n "$ERROR_CODE" ]] && [[ "$ERROR_CODE" =~ MISSING_RULE_DESCRIPTION_AT_INDEX_([0-9]+) ]]; then
    INDEX="${BASH_REMATCH[1]}"
  fi
elif grep -q "YAML parse failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="YAML_PARSE_ERROR"
  FILEPATH="$(grep -o "filepath: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/filepath: '\(.*\)'/\1/" || true)"
elif grep -q "File load failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="$(grep -o "error_code: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/error_code: '\(.*\)'/\1/" || true)"
  FILEPATH="$(grep -o "filepath: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/filepath: '\(.*\)'/\1/" || true)"
fi

[[ -z "$ERROR_CODE" ]] && ERROR_CODE="POLICY_LOAD_FAILED"

echo "POLICY_HEADERS_SCHEMA_V1_OK=0"
echo "ERROR_CODE=${ERROR_CODE}"
echo "INDEX=${INDEX:-}"
echo "FILEPATH=${FILEPATH:-}"
exit 1
