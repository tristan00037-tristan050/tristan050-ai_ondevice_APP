#!/usr/bin/env bash
set -euo pipefail

# P22-P2-05: sources enforce_spec_v1.sh lib (ENFORCE_SPEC_V1 compliant)
# shellcheck source=scripts/verify/lib/enforce_spec_v1.sh
. scripts/verify/lib/enforce_spec_v1.sh

BUNDLE_LOCK_V1_POLICY_OK=0
BUNDLE_LOCK_V1_REPORT_PRESENT_OK=0
BUNDLE_LOCK_V1_SCHEMA_OK=0
trap 'echo "BUNDLE_LOCK_V1_POLICY_OK=${BUNDLE_LOCK_V1_POLICY_OK}"; echo "BUNDLE_LOCK_V1_REPORT_PRESENT_OK=${BUNDLE_LOCK_V1_REPORT_PRESENT_OK}"; echo "BUNDLE_LOCK_V1_SCHEMA_OK=${BUNDLE_LOCK_V1_SCHEMA_OK}"' EXIT

if ! enforce_spec_should_enforce "BUNDLE_LOCK_V1"; then
  enforce_spec_emit_skip "BUNDLE_LOCK_V1_POLICY"
  enforce_spec_emit_skip "BUNDLE_LOCK_V1_REPORT_PRESENT"
  enforce_spec_emit_skip "BUNDLE_LOCK_V1_SCHEMA"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/BUNDLE_LOCK_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=BUNDLE_LOCK_SSOT_MISSING"; exit 1; }
grep -q '^BUNDLE_LOCK_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=BUNDLE_LOCK_TOKEN_MISSING"; exit 1; }
# P22-P2-01: verify gen_bundle_lock_v1.sh fields
grep -q '^REQUIRED_FIELDS=.*bundle_lock_version' "$SSOT" || { echo "ERROR_CODE=BUNDLE_LOCK_FIELD_DEF_MISSING"; exit 1; }
grep -q '^REQUIRED_FIELDS=.*lock_digest_sha256' "$SSOT" || { echo "ERROR_CODE=BUNDLE_LOCK_DIGEST_FIELD_MISSING"; exit 1; }
BUNDLE_LOCK_V1_POLICY_OK=1

OUTPUT_PATH="$(grep '^OUTPUT_PATH=' "$SSOT" | head -1 | sed 's/^OUTPUT_PATH=//' | tr -d '\r')"
[[ -n "$OUTPUT_PATH" ]] || { echo "ERROR_CODE=BUNDLE_LOCK_OUTPUT_PATH_MISSING"; exit 1; }
[[ -f "$ROOT/$OUTPUT_PATH" ]] || { echo "ERROR_CODE=BUNDLE_LOCK_REPORT_MISSING"; echo "EXPECTED=$OUTPUT_PATH"; exit 1; }
BUNDLE_LOCK_V1_REPORT_PRESENT_OK=1

REQUIRED_FIELDS="$(grep '^REQUIRED_FIELDS=' "$SSOT" | head -1 | sed 's/^REQUIRED_FIELDS=//' | tr -d '\r')"
[[ -n "$REQUIRED_FIELDS" ]] || { echo "ERROR_CODE=BUNDLE_LOCK_REQUIRED_FIELDS_MISSING"; exit 1; }

IFS=',' read -ra FIELDS <<< "$REQUIRED_FIELDS"
for field in "${FIELDS[@]}"; do
  field="$(echo "$field" | tr -d ' ')"
  grep -q "\"$field\"" "$ROOT/$OUTPUT_PATH" || {
    echo "ERROR_CODE=BUNDLE_LOCK_FIELD_MISSING"
    echo "MISSING_FIELD=$field"
    exit 1
  }
done
BUNDLE_LOCK_V1_SCHEMA_OK=1
exit 0
