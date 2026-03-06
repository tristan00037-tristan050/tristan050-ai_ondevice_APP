#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_INTEGRITY_POLICY_V1_OK=0
ARTIFACT_BUNDLE_COMPONENTS_PRESENT_OK=0
ARTIFACT_BUNDLE_CROSS_REF_MATCH_OK=0
trap 'echo "ARTIFACT_BUNDLE_INTEGRITY_POLICY_V1_OK=${ARTIFACT_BUNDLE_INTEGRITY_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_COMPONENTS_PRESENT_OK=${ARTIFACT_BUNDLE_COMPONENTS_PRESENT_OK}"; echo "ARTIFACT_BUNDLE_CROSS_REF_MATCH_OK=${ARTIFACT_BUNDLE_CROSS_REF_MATCH_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_INTEGRITY_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_INTEGRITY_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_INTEGRITY_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_INTEGRITY_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_INTEGRITY_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_BUNDLE_INTEGRITY_SSOT_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

get_ssot_var() {
  local key="$1"
  local default="$2"
  if grep -qE "^${key}=" "$SSOT" 2>/dev/null; then
    grep -E "^${key}=" "$SSOT" | head -n1 | sed "s/^${key}=//" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  else
    echo "$default"
  fi
}
TUF_META_ROOT="$(get_ssot_var "TUF_META_ROOT" "out/ops/tuf")"
ARTIFACT_MANIFEST_PATH="$(get_ssot_var "ARTIFACT_MANIFEST_PATH" "out/ops/artifacts/manifest.json")"
ARTIFACT_DIGEST_PATH="$(get_ssot_var "ARTIFACT_DIGEST_PATH" "out/ops/artifacts/digest.json")"
ARTIFACT_SBOM_PATH="$(get_ssot_var "ARTIFACT_SBOM_PATH" "out/ops/sbom/from_artifacts.cdx.json")"

# 1) 필수 구성요소 존재
if [ ! -d "$TUF_META_ROOT" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_COMPONENT_MISSING"
  echo "HIT_PATH=$TUF_META_ROOT"
  exit 1
fi
if [ ! -f "$ARTIFACT_MANIFEST_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_COMPONENT_MISSING"
  echo "HIT_PATH=$ARTIFACT_MANIFEST_PATH"
  exit 1
fi
if [ ! -f "$ARTIFACT_DIGEST_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_COMPONENT_MISSING"
  echo "HIT_PATH=$ARTIFACT_DIGEST_PATH"
  exit 1
fi
if [ ! -f "$ARTIFACT_SBOM_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_COMPONENT_MISSING"
  echo "HIT_PATH=$ARTIFACT_SBOM_PATH"
  exit 1
fi
ARTIFACT_BUNDLE_COMPONENTS_PRESENT_OK=1

# 2) TUF 최소 역할 파일
for role in root targets snapshot timestamp; do
  if [ ! -f "${TUF_META_ROOT}/${role}.json" ]; then
    echo "ERROR_CODE=ARTIFACT_BUNDLE_TUF_MISSING"
    echo "HIT_ROLE=$role"
    exit 1
  fi
done

# 3) JSON 파싱 + manifest↔digest 정합 + manifest↔SBOM 참조 정합
command -v node >/dev/null 2>&1 || {
  echo "ERROR_CODE=ARTIFACT_BUNDLE_JSON_INVALID"
  exit 1
}
set +e
node -e "
const fs = require('fs');
const manifestPath = process.argv[2];
const digestPath = process.argv[3];
const sbomPath = process.argv[4];
const expectedSbomPath = process.argv[5];
let manifest, digest, sbom;
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
} catch (e) { process.exit(10); }
if (!manifest || typeof manifest !== 'object') process.exit(10);
try {
  digest = JSON.parse(fs.readFileSync(digestPath, 'utf8'));
} catch (e) { process.exit(10); }
if (!digest || typeof digest !== 'object') process.exit(10);
try {
  sbom = JSON.parse(fs.readFileSync(sbomPath, 'utf8'));
} catch (e) { process.exit(10); }
if (!sbom || typeof sbom !== 'object') process.exit(10);

// manifest ↔ digest
const digestVal = digest.sha || digest.digest;
const manifestVal = manifest.sha || manifest.digest;
if (typeof digestVal !== 'string' || !digestVal) process.exit(11);
if (typeof manifestVal !== 'string' || manifestVal !== digestVal) process.exit(11);

// manifest ↔ SBOM 참조/경로 정합: manifest에 sbomPath/sbom 등이 있으면 해당 값이 expectedSbomPath와 일치하거나 포함
const manifestSbomRef = manifest.sbomPath || manifest.sbom || manifest.bomPath || '';
if (expectedSbomPath && manifestSbomRef && typeof manifestSbomRef === 'string') {
  const norm = (p) => p.replace(/\\\\/g, '/');
  if (norm(manifestSbomRef) !== norm(expectedSbomPath) && !norm(manifestSbomRef).endsWith(expectedSbomPath.replace(/^.*\//, ''))) process.exit(12);
}
// SBOM 최소 구조
if (!sbom.bomFormat || !Array.isArray(sbom.components)) process.exit(12);
process.exit(0);
" "$ARTIFACT_MANIFEST_PATH" "$ARTIFACT_DIGEST_PATH" "$ARTIFACT_SBOM_PATH" "$ARTIFACT_SBOM_PATH" 2>/dev/null
rc=$?
set -e
if [ "$rc" -eq 10 ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_JSON_INVALID"
  exit 1
fi
if [ "$rc" -eq 11 ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_MANIFEST_MISMATCH"
  exit 1
fi
if [ "$rc" -eq 12 ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_SBOM_MISMATCH"
  exit 1
fi
if [ "$rc" -ne 0 ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_INTEGRITY_UNEXPECTED_RC"
  echo "HIT_RC=$rc"
  exit 1
fi

ARTIFACT_BUNDLE_CROSS_REF_MATCH_OK=1
ARTIFACT_BUNDLE_INTEGRITY_POLICY_V1_OK=1
exit 0
