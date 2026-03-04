#!/usr/bin/env bash
set -euo pipefail

ENFORCE_SPEC_V1_OK=0
finish(){ echo "ENFORCE_SPEC_V1_OK=${ENFORCE_SPEC_V1_OK}"; }
trap finish EXIT

SSOT="docs/ops/contracts/ENFORCE_SPEC_V1.md"
LIB="scripts/verify/lib/enforce_spec_v1.sh"
test -f "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING"; echo "HIT_PATH=$SSOT"; exit 1; }
grep -q '^ENFORCE_SPEC_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_INVALID"; echo "HIT_PATH=$SSOT"; exit 1; }
test -f "$LIB" || { echo "ERROR_CODE=LIB_MISSING"; echo "HIT_PATH=$LIB"; exit 1; }

# Enforce: target verifiers must source the lib and must not directly parse *_ENFORCE
targets=(
  "scripts/verify/verify_model_pack_sbom_cyclonedx_v1.sh"
  "scripts/verify/verify_secure_update_tuf_principles_v1.sh"
)

for f in "${targets[@]}"; do
  test -f "$f" || { echo "ERROR_CODE=TARGET_MISSING"; echo "HIT_PATH=$f"; exit 1; }
  grep -qF ". ${LIB}" "$f" || grep -qF "source ${LIB}" "$f" || { echo "ERROR_CODE=LIB_NOT_SOURCED"; echo "HIT_PATH=$f"; exit 1; }
  # direct parsing ban: pattern *_ENFORCE:- or ${..._ENFORCE
  if grep -qE '[_A-Z0-9]+_ENFORCE(:-|[}])' "$f"; then
    echo "ERROR_CODE=DIRECT_ENFORCE_PARSE_FOUND"
    echo "HIT_PATH=$f"
    exit 1
  fi
done

ENFORCE_SPEC_V1_OK=1
exit 0
