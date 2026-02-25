#!/usr/bin/env bash
# POLICY_HEADERS_SCHEMA_V1 (PR-P0-D01): Policy file paths fixed (repo-relative). Rule-level description check. Meta-only.
# 실패 시: POLICY_HEADERS_SCHEMA_V1_OK=0, ERROR_CODE, INDEX만 출력 후 exit 1
# 성공 시: POLICY_HEADERS_SCHEMA_V1_OK=1, POLICY_HEADERS_RULE_DESCRIPTION_PRESENT_OK=1 출력 후 exit 0
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# 정책 파일 경로 (레포 실제 경로 기준, loader와 동일)
POLICY_BASE="${REPO_ROOT}/webcore_appcore_starter_4_17/policy"
POLICY_HEADERS="${POLICY_BASE}/headers.yaml"
POLICY_EXPORT="${POLICY_BASE}/export.yaml"
POLICY_META_ONLY="${POLICY_BASE}/meta_only.yaml"

LOADER_DIST="${REPO_ROOT}/webcore_appcore_starter_4_17/packages/bff-accounting/dist/policy/loader.js"
if [[ ! -f "$LOADER_DIST" ]]; then
  echo "POLICY_HEADERS_SCHEMA_V1_OK=0"
  echo "ERROR_CODE=FILE_NOT_FOUND"
  echo "INDEX="
  exit 1
fi

stderr_file="$(mktemp)"
trap 'rm -f "$stderr_file"' EXIT

if node scripts/verify/run_policy_headers_schema_check.mjs 2>"$stderr_file"; then
  # mjs already prints POLICY_HEADERS_SCHEMA_V1_OK=1 and POLICY_HEADERS_RULE_DESCRIPTION_PRESENT_OK=1
  exit 0
fi

# 실패: meta-only — ERROR_CODE, INDEX만 출력 (FILEPATH 미출력)
ERROR_CODE=""
INDEX=""
if grep -q "Schema validation failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="$(grep -o "error_code: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/error_code: '\(.*\)'/\1/" || true)"
  if [[ -n "$ERROR_CODE" ]] && [[ "$ERROR_CODE" =~ _AT_INDEX_([0-9]+)$ ]]; then
    INDEX="${BASH_REMATCH[1]}"
  fi
elif grep -q "YAML parse failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="YAML_PARSE_ERROR"
elif grep -q "File load failed" "$stderr_file" 2>/dev/null; then
  ERROR_CODE="$(grep -o "error_code: '[^']*'" "$stderr_file" 2>/dev/null | head -1 | sed "s/error_code: '\(.*\)'/\1/" || true)"
fi

[[ -z "$ERROR_CODE" ]] && ERROR_CODE="POLICY_LOAD_FAILED"

echo "POLICY_HEADERS_SCHEMA_V1_OK=0"
echo "ERROR_CODE=${ERROR_CODE}"
echo "INDEX=${INDEX:-}"
exit 1
