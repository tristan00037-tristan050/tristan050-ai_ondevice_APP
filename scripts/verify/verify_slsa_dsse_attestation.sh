#!/usr/bin/env bash
set -euo pipefail

SUBJ=".artifacts/supplychain_subject.txt"

# CI에서 GH_TOKEN 존재를 하드게이트(원인 즉시 식별)
if [[ -n "${GITHUB_RUN_ID:-}" && -z "${GH_TOKEN:-}" ]]; then
  echo "BLOCK: GH_TOKEN missing in CI"
  echo "GH_TOKEN_PRESENT_OK=0"
  exit 1
fi
echo "GH_TOKEN_PRESENT_OK=1"

# 로컬에서는 파일이 없으면 SKIP(개발 편의)
if [[ ! -f "$SUBJ" ]]; then
  if [[ -n "${GITHUB_RUN_ID:-}" ]]; then
    echo "FAIL: DSSE attestation subject missing: ${SUBJ}"
    echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=0"
    echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=0"
    echo "SLSA_DSSE_ACTOR_IDENTITY_OK=0"
    echo "GH_ATTESTATION_VERIFY_STRICT_OK=0"
    exit 1
  fi
  echo "== guard: DSSE attestation (SKIP: local/no subject file) =="
  exit 0
fi

command -v gh >/dev/null 2>&1 || { echo "BLOCK: gh not found"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

# gh 버전 하한(정책적으로 고정). CI에서 부족하면 즉시 FAIL.
MIN_MAJOR=2
MIN_MINOR=67

ver_line="$(gh --version | head -n 1 || true)"
# 예: gh version 2.70.0 (2025-xx-xx)
ver="$(echo "$ver_line" | awk "{print \$3}")"
maj="$(echo "$ver" | cut -d. -f1)"
min="$(echo "$ver" | cut -d. -f2)"

if [[ -z "${maj:-}" || -z "${min:-}" ]]; then
  echo "BLOCK: cannot parse gh version: $ver_line"
  exit 1
fi

if (( maj < MIN_MAJOR )) || { (( maj == MIN_MAJOR )) && (( min < MIN_MINOR )); }; then
  echo "BLOCK: gh version too old: ${ver} (need >= ${MIN_MAJOR}.${MIN_MINOR}.x)"
  echo "GH_ATTESTATION_VERIFY_STRICT_OK=0"
  exit 1
fi

OUT="$(mktemp)"
set +e
gh attestation verify "$SUBJ" -R "${GITHUB_REPOSITORY}" \
  --predicate-type "https://slsa.dev/provenance/v1" \
  --signer-workflow "github.com/${GITHUB_REPOSITORY}/.github/workflows/product-verify-supplychain.yml" \
  --deny-self-hosted-runners \
  --format json >"$OUT" 2>&1
rc=$?
set -e

# exit code만 믿지 않고 JSON 정책으로 fail-closed
if [[ $rc -ne 0 ]]; then
  cat "$OUT" >&2 || true
  echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
  echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=0"
  echo "SLSA_DSSE_ACTOR_IDENTITY_OK=0"
  echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
  exit 1
fi

jq -e 'type=="array" and length>=1' "$OUT" >/dev/null 2>&1 || {
  cat "$OUT" >&2 || true
  echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
  echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=0"
  echo "SLSA_DSSE_ACTOR_IDENTITY_OK=0"
  echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
  exit 1
}

echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=1"
echo "SLSA_DSSE_ACTOR_IDENTITY_OK=1"
echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
# GH_TOKEN_PRESENT_OK is already output above
