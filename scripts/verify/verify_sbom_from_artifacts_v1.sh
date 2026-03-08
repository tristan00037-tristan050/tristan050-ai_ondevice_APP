#!/usr/bin/env bash
set -euo pipefail

SBOM_FROM_ARTIFACTS_POLICY_V1_OK=0
SBOM_FROM_ARTIFACTS_PRESENT_OK=0
SBOM_FROM_ARTIFACTS_SCHEMA_OK=0
trap 'echo "SBOM_FROM_ARTIFACTS_POLICY_V1_OK=${SBOM_FROM_ARTIFACTS_POLICY_V1_OK}"; echo "SBOM_FROM_ARTIFACTS_PRESENT_OK=${SBOM_FROM_ARTIFACTS_PRESENT_OK}"; echo "SBOM_FROM_ARTIFACTS_SCHEMA_OK=${SBOM_FROM_ARTIFACTS_SCHEMA_OK}"' EXIT

ENFORCE="${SBOM_FROM_ARTIFACTS_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "SBOM_FROM_ARTIFACTS_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/SBOM_FROM_ARTIFACTS_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=SBOM_FROM_ARTIFACTS_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'SBOM_FROM_ARTIFACTS_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=SBOM_FROM_ARTIFACTS_SSOT_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

# SBOM_ARTIFACT_PATH from SSOT or default
SBOM_ARTIFACT_PATH=""
if grep -qE '^SBOM_ARTIFACT_PATH=' "$SSOT" 2>/dev/null; then
  SBOM_ARTIFACT_PATH="$(grep -E '^SBOM_ARTIFACT_PATH=' "$SSOT" | head -n1 | sed 's/^SBOM_ARTIFACT_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
[ -n "$SBOM_ARTIFACT_PATH" ] || SBOM_ARTIFACT_PATH="out/ops/sbom/from_artifacts.cdx.json"

# 1) Present: artifact path에 SBOM 파일 존재
if [ ! -f "$SBOM_ARTIFACT_PATH" ]; then
  echo "ERROR_CODE=SBOM_ARTIFACT_MISSING"
  echo "HIT_PATH=$SBOM_ARTIFACT_PATH"
  exit 1
fi
SBOM_FROM_ARTIFACTS_PRESENT_OK=1

# 2) JSON 파싱 + 최소 키(bomFormat, specVersion, components)
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR_CODE=SBOM_JSON_CHECK_UNAVAILABLE"
  echo "HIT_REASON=node_not_found"
  exit 1
fi
set +e
node -e "
  const fs = require('fs');
  const { EXIT } = require('./tools/verify-runtime/exit_codes_v1.cjs');
  let d;
  try { d = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); } catch (e) { process.exit(EXIT.JSON_INVALID); }
  if (!d || typeof d !== 'object') process.exit(EXIT.JSON_INVALID);
  if (typeof d.bomFormat !== 'string') process.exit(EXIT.SCHEMA_MISSING);
  if (typeof d.specVersion !== 'string' && typeof d.specVersion !== 'number') process.exit(EXIT.SCHEMA_MISSING);
  if (!Array.isArray(d.components)) process.exit(EXIT.SCHEMA_MISSING);
  process.exit(0);
" "$SBOM_ARTIFACT_PATH" 2>/dev/null
r=$?
set -e
if [ "$r" -eq 10 ]; then
  echo "ERROR_CODE=SBOM_JSON_INVALID"
  echo "HIT_PATH=$SBOM_ARTIFACT_PATH"
  exit 1
fi
if [ "$r" -eq 11 ]; then
  echo "ERROR_CODE=SBOM_SCHEMA_MISSING"
  echo "HIT_PATH=$SBOM_ARTIFACT_PATH"
  exit 1
fi
SBOM_FROM_ARTIFACTS_SCHEMA_OK=1
SBOM_FROM_ARTIFACTS_POLICY_V1_OK=1

exit 0
