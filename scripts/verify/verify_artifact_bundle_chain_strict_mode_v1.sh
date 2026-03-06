#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=0
ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=0
ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=0
trap 'echo "ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
}

ANCHOR_PATH="scripts/verify/verify_repo_contracts.sh"
if grep -qE '^ANCHOR_PATH=' "$SSOT" 2>/dev/null; then
  ANCHOR_PATH="$(grep -E '^ANCHOR_PATH=' "$SSOT" | head -n1 | sed 's/^ANCHOR_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
if [ ! -f "$ANCHOR_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$ANCHOR_PATH"
  exit 1
fi

# 스크립트명 → 해당 ENFORCE 변수명 (strict chain 6개)
get_enforce_var() {
  case "$1" in
    verify_tuf_min_signing_chain_v1.sh) echo "TUF_MIN_SIGNING_CHAIN_ENFORCE" ;;
    verify_sbom_from_artifacts_v1.sh) echo "SBOM_FROM_ARTIFACTS_ENFORCE" ;;
    verify_artifact_manifest_bind_v1.sh) echo "ARTIFACT_MANIFEST_BIND_ENFORCE" ;;
    verify_artifact_bundle_integrity_v1.sh) echo "ARTIFACT_BUNDLE_INTEGRITY_ENFORCE" ;;
    verify_artifact_bundle_provenance_link_v1.sh) echo "ARTIFACT_BUNDLE_PROVENANCE_LINK_ENFORCE" ;;
    verify_artifact_bundle_verifier_chain_v1.sh) echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE" ;;
    *) echo "" ;;
  esac
}

for script in verify_tuf_min_signing_chain_v1.sh verify_sbom_from_artifacts_v1.sh verify_artifact_manifest_bind_v1.sh verify_artifact_bundle_integrity_v1.sh verify_artifact_bundle_provenance_link_v1.sh verify_artifact_bundle_verifier_chain_v1.sh; do
  envar="$(get_enforce_var "$script")"
  [ -n "$envar" ] || continue
  line_no=""
  if ! grep -qF "$script" "$ANCHOR_PATH"; then
    echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
    echo "HIT_SCRIPT=$script"
    exit 1
  fi
  # run_guard ... script 포함하는 줄 번호 (숫자만 추출)
  line_no="$(grep -n "run_guard" "$ANCHOR_PATH" | grep -F "$script" | head -1 | sed -n 's/^\([0-9][0-9]*\):.*/\1/p')"
  if [[ -z "$line_no" || ! "$line_no" =~ ^[0-9]+$ ]]; then
    echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
    echo "HIT_SCRIPT=$script"
    exit 1
  fi
  # 해당 줄 + 직전 줄에서 ENFORCE 변수 확인
  block_lines="$(sed -n "$((line_no-1)),${line_no}p" "$ANCHOR_PATH" 2>/dev/null)"
  if [[ "$block_lines" != *"$envar"* ]]; then
    echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_ENFORCE_MISSING"
    echo "HIT_SCRIPT=$script"
    exit 1
  fi
  # fail-open: ENFORCE=0 고정이면 안 됨 (:-0 기본값은 허용)
  if echo "$block_lines" | grep -qE "(^|[^:])${envar}=0([^0-9]|\$)"; then
    echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_FAILOPEN_DETECTED"
    echo "HIT_SCRIPT=$script"
    exit 1
  fi
done

ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=1
ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=1
ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=1
exit 0
