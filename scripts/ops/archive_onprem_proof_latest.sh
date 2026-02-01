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

# 어떤 이유로든 실패/종료하면 TMP는 반드시 삭제(민감 내용 잔존 방지)
cleanup_tmp() { rm -f "$TMP"; }
trap cleanup_tmp EXIT INT TERM

# 1) 복사본 생성
cp -f "$LATEST" "$TMP"

# 2) 민감패턴 스캔(FAIL이면 즉시 실패, trap이 TMP 삭제)
if grep -nFf "$PATTERNS" "$TMP" >/dev/null; then
  echo "BLOCK: sensitive pattern detected in proof (refuse to archive)"
  grep -nFf "$PATTERNS" "$TMP" | sed 's/:.*$//' | head -n 20 || true
  exit 1
fi

# 3) 비정상적으로 긴 라인(예: base64 blob) 차단: 내용 출력 금지(라인 번호/길이만)
awk 'length($0) > 500 { print "BLOCK: long line at " NR " len=" length($0); exit 1 }' "$TMP"

# 4) PASS면 이동(확정). 이동 후 TMP는 없어지고, trap cleanup은 영향 없음
mv -f "$TMP" "$OUT"
echo "OK: archived to $OUT"
