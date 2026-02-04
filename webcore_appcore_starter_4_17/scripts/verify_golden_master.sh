#!/usr/bin/env bash
set -euo pipefail

# ✅ S6-S7: Golden Master 검증 게이트 (범용, manifest 인자화)
# 사용법: bash scripts/verify_golden_master.sh --manifest <path>

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

MANIFEST=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --manifest)
      MANIFEST="$2"
      shift 2
      ;;
    *)
      echo "Usage: $0 --manifest <path>"
      exit 1
      ;;
  esac
done

if [ -z "$MANIFEST" ]; then
  # 기본값: S6 seal manifest
  MANIFEST="$ROOT/docs/ops/r10-s6-seal-manifest.json"
fi

if [ ! -f "$MANIFEST" ]; then
  echo "[FAIL] manifest not found: $MANIFEST"
  exit 1
fi

echo "[verify] Golden Master Verification"
echo "[info] manifest: $MANIFEST"

FAILURES=()

# 1) (비파괴) generate_s6_seal_artifacts.sh 실행
# manifest 경로에서 generate 스크립트 추론
if [[ "$MANIFEST" =~ r10-s6-seal-manifest\.json$ ]]; then
  echo "[step] 1) Generate seal artifacts (non-destructive)"
  if [ -f "$ROOT/scripts/generate_s6_seal_artifacts.sh" ]; then
    if ! bash "$ROOT/scripts/generate_s6_seal_artifacts.sh"; then
      FAILURES+=("generate_s6_seal_artifacts.sh failed")
    else
      echo "[OK] seal artifacts generated"
    fi
  else
    echo "[warn] generate_s6_seal_artifacts.sh not found, skipping"
  fi
else
  echo "[info] non-S6 manifest, skipping generate step"
fi

# 2) verify_ops_proof_manifest.sh PASS
echo "[step] 2) Verify ops proof manifest"
if [ -f "$ROOT/scripts/verify_ops_proof_manifest.sh" ]; then
  if ! bash "$ROOT/scripts/verify_ops_proof_manifest.sh"; then
    FAILURES+=("verify_ops_proof_manifest.sh failed")
  else
    echo "[OK] ops proof manifest verified"
  fi
else
  FAILURES+=("verify_ops_proof_manifest.sh not found")
fi

# 3) checksums.txt.sha256 검증 PASS
echo "[step] 3) Verify checksums SHA256"
OPS_DIR="$(dirname "$MANIFEST")"
CHECKSUMS="$OPS_DIR/r10-s6-seal-checksums.txt"
CHECKSUMS_SHA="$OPS_DIR/r10-s6-seal-checksums.txt.sha256"

if [ -f "$CHECKSUMS" ] && [ -f "$CHECKSUMS_SHA" ]; then
  stored_sha=$(awk '{print $1}' "$CHECKSUMS_SHA" 2>/dev/null | head -1)
  
  if [ -z "$stored_sha" ]; then
    FAILURES+=("checksums.txt.sha256 is empty")
  else
    if command -v shasum >/dev/null 2>&1; then
      actual_sha=$(shasum -a 256 "$CHECKSUMS" | cut -d' ' -f1)
    elif command -v sha256sum >/dev/null 2>&1; then
      actual_sha=$(sha256sum "$CHECKSUMS" | cut -d' ' -f1)
    else
      FAILURES+=("no sha256 command found")
      actual_sha=""
    fi
    
    if [ -n "$actual_sha" ] && [ "$actual_sha" != "$stored_sha" ]; then
      FAILURES+=("checksums.txt integrity mismatch: actual=$actual_sha, stored=$stored_sha")
    elif [ -n "$actual_sha" ]; then
      echo "[OK] checksums.txt.sha256 verified"
    fi
  fi
else
  echo "[warn] checksums files not found, skipping"
fi

# 결과 판정
if [ ${#FAILURES[@]} -gt 0 ]; then
  echo "[FAIL] Golden Master Verification"
  for failure in "${FAILURES[@]}"; do
    echo "  - $failure"
  done
  exit 1
else
  echo "[PASS] Golden Master Verification"
  exit 0
fi

