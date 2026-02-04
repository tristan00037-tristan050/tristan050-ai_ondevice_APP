#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh

OUT_DIR="docs/ops"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG="$OUT_DIR/r10-s7-retriever-quality-proof-${TS}.log"
LATEST="$OUT_DIR/r10-s7-retriever-quality-proof.latest"

cleanup_old() {
  # keep newest 1 log (portable: no xargs -r, no mapfile)
  i=0
  for f in $(ls -1t "$OUT_DIR"/r10-s7-retriever-quality-proof-*.log 2>/dev/null || true); do
    i=$((i+1))
    if [ "$i" -gt 1 ]; then rm -f "$f"; fi
  done
}

{
  echo "== START PROVE_RETRIEVER_QUALITY =="
  echo "TS=$TS"
  echo "PWD=$(pwd)"
  echo "== VERIFY =="
  bash scripts/ops/verify_retriever_quality.sh
  echo "== REPORT (meta-only, top 60) =="
  sed -n "1,60p" docs/ops/r10-s7-retriever-quality-phase0-report.json || true
  echo "== END PROVE_RETRIEVER_QUALITY =="
} | tee "$LOG" >/dev/null

echo "$(basename "$LOG")" > "$LATEST"
cleanup_old

echo "OK: proof log=$LOG"
echo "OK: latest -> $(cat "$LATEST")"

