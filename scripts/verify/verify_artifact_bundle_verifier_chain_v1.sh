#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=0
ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=0
ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=0
trap 'echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK}"; echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_VERIFIER_CHAIN_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_VERIFIER_CHAIN_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
}

ANCHOR_PATH="scripts/verify/verify_repo_contracts.sh"
if grep -qE '^ANCHOR_PATH=' "$SSOT" 2>/dev/null; then
  ANCHOR_PATH="$(grep -E '^ANCHOR_PATH=' "$SSOT" | head -n1 | sed 's/^ANCHOR_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
if [ ! -f "$ANCHOR_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_WIRING_MISSING"
  echo "HIT_PATH=$ANCHOR_PATH"
  exit 1
fi

# 고정 체인 순서 (SSOT와 동일)
CHAIN=(
  "verify_tuf_min_signing_chain_v1.sh"
  "verify_sbom_from_artifacts_v1.sh"
  "verify_artifact_manifest_bind_v1.sh"
  "verify_artifact_bundle_integrity_v1.sh"
  "verify_artifact_bundle_provenance_link_v1.sh"
)

# 앵커 파일에서 위 스크립트 이름이 첫 등장하는 순서만 수집
found=()
seen=()
for i in "${!CHAIN[@]}"; do seen+=( 0 ); done
while IFS= read -r line; do
  for i in "${!CHAIN[@]}"; do
    [ "${seen[$i]}" -eq 1 ] && continue
    if [[ "$line" == *"${CHAIN[$i]}"* ]]; then
      found+=( "$i" )
      seen[$i]=1
      break
    fi
  done
done < "$ANCHOR_PATH"

# 1) 5개 모두 존재하는지
for i in "${!CHAIN[@]}"; do
  if [ "${seen[$i]:-0}" -ne 1 ]; then
    echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_MISSING"
    echo "HIT_SCRIPT=${CHAIN[$i]}"
    exit 1
  fi
done
ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=1

# 2) 첫 등장 순서가 규약 순서와 일치하는지 (found[]가 0,1,2,3,4 여야 함)
for idx in "${!found[@]}"; do
  [ "${found[$idx]}" -eq "$idx" ] || {
    echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_ORDER_INVALID"
    echo "HIT_PATH=$ANCHOR_PATH"
    exit 1
  }
done
ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=1
ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=1
exit 0
