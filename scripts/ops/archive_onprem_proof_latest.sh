#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"
PATTERNS="docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt"
ARCH_DIR="docs/ops/PROOFS/archive"
DATE="$(date -u +%F)"
OUT="${ARCH_DIR}/${DATE}_onprem_real_world_proof.md"
TMP="${OUT}.tmp"

[[ -s "$LATEST" ]] || { echo "BLOCK: LATEST missing/empty: $LATEST"; exit 1; }
[[ -s "$PATTERNS" ]] || { echo "BLOCK: patterns missing/empty: $PATTERNS"; exit 1; }

mkdir -p "$ARCH_DIR"
cp -f "$LATEST" "$TMP"

# 민감패턴 적발 시: 내용 출력 금지(라인 번호만), 즉시 삭제 후 실패
if grep -nFf "$PATTERNS" "$TMP" >/dev/null; then
  echo "BLOCK: sensitive pattern detected in proof (refuse to archive)"
  grep -nFf "$PATTERNS" "$TMP" | sed 's/:.*$//' | head -n 20 || true
  rm -f "$TMP"
  exit 1
fi

# 비정상적으로 긴 라인(예: base64 blob) 차단: 내용 출력 금지(라인 번호/길이만)
awk 'length($0) > 500 { print "BLOCK: long line at " NR " len=" length($0); exit 1 }' "$TMP"

mv -f "$TMP" "$OUT"
echo "OK: archived to $OUT"
