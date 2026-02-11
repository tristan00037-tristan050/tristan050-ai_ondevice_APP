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
# Attestation이 업로드될 때까지 최대 60초 대기 (재시도 로직)
MAX_RETRIES=12
RETRY_DELAY=5
rc=1
for i in $(seq 1 $MAX_RETRIES); do
  gh attestation verify "$SUBJ" -R "${GITHUB_REPOSITORY}" \
    --predicate-type "https://slsa.dev/provenance/v1" \
    --signer-workflow "github.com/${GITHUB_REPOSITORY}/.github/workflows/product-verify-supplychain.yml" \
    --deny-self-hosted-runners \
    --cert-oidc-issuer "https://token.actions.githubusercontent.com" \
    --format json >"$OUT" 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    break
  fi
  if [[ $i -lt $MAX_RETRIES ]]; then
    sleep $RETRY_DELAY
  fi
done
set -e

if [[ $rc -ne 0 ]]; then
  # 원문 출력 금지(code-only)
  # 재시도 횟수 정보는 code-only로 제공
  echo "ERROR_CODE=GH_ATTESTATION_VERIFY_FAILED"
  echo "ERROR_RETRIES=${MAX_RETRIES}"
  echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
  echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=0"
  echo "SLSA_DSSE_ACTOR_IDENTITY_OK=0"
  echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
  exit 1
fi

jq -e 'type=="array" and length>=1' "$OUT" >/dev/null 2>&1 || {
  # 원문 출력 금지(code-only)
  echo "ERROR_CODE=GH_ATTESTATION_VERIFY_JSON_INVALID"
  echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
  echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=0"
  echo "SLSA_DSSE_ACTOR_IDENTITY_OK=0"
  echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
  exit 1
}

# H3.5-SUPPLYCHAIN-01: SSOT 기반 identity 제약 강화 (CI에서만)
if [[ -n "${GITHUB_RUN_ID:-}" && -n "${GITHUB_REPOSITORY:-}" ]]; then
  SSOT="docs/ops/contracts/SUPPLYCHAIN_SIGNER_SSOT.json"
  if [[ -f "$SSOT" ]]; then
    REPO_SSOT="$(jq -r ".repo_full_name" "$SSOT")"
    WF_PATH_SSOT="$(jq -r ".signer_workflow_path" "$SSOT")"
    ACTOR_ALLOW_0="$(jq -r ".allowed_actor_logins[0]" "$SSOT")"

    # 현재 repo 일치
    if [[ "${GITHUB_REPOSITORY}" != "${REPO_SSOT}" ]]; then
      echo "SLSA_DSSE_REPO_IDENTITY_OK=0"
      exit 1
    fi
    echo "SLSA_DSSE_REPO_IDENTITY_OK=1"

    # 워크플로 경로는 gh verify 옵션으로 이미 강제하지만, 문서/SSOT 일치도 확인
    if [[ "${WF_PATH_SSOT}" != ".github/workflows/product-verify-supplychain.yml" ]]; then
      echo "SLSA_DSSE_SIGNER_WORKFLOW_OK=0"
      exit 1
    fi
    echo "SLSA_DSSE_SIGNER_WORKFLOW_OK=1"

    # actor allowlist(최소 1개)
    if [[ -n "${GITHUB_ACTOR:-}" && "${GITHUB_ACTOR}" != "${ACTOR_ALLOW_0}" ]]; then
      echo "SLSA_DSSE_ACTOR_ALLOWLIST_OK=0"
      exit 1
    fi
    echo "SLSA_DSSE_ACTOR_ALLOWLIST_OK=1"
  fi
fi

echo "SLSA_DSSE_ATTESTATION_PRESENT_OK=1"
echo "SLSA_DSSE_ATTESTATION_VERIFY_OK=1"
echo "SLSA_DSSE_ACTOR_IDENTITY_OK=1"
echo "GH_ATTESTATION_VERIFY_STRICT_OK=1"
# GH_TOKEN_PRESENT_OK is already output above
