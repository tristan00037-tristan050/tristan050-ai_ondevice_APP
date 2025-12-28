#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh

OUT_DIR="docs/ops"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG="$OUT_DIR/r10-s7-retriever-baseline-proof-${TS}.log"
LATEST="$OUT_DIR/r10-s7-retriever-baseline-proof.latest"

cleanup_old() {
  i=0
  for f in $(ls -1t "$OUT_DIR"/r10-s7-retriever-baseline-proof-*.log 2>/dev/null || true); do
    i=$((i+1))
    if [ "$i" -gt 1 ]; then rm -f "$f"; fi
  done
}

{
  echo "== START PROVE_BASELINE_RATCHET =="
  echo "TS=$TS"
  echo "PWD=$(pwd)"
  echo "== UPDATE BASELINE (ratchet) =="
  bash scripts/ops/update_retriever_baseline.sh --update-baseline
  echo "== META_ONLY_DEBUG (scan list proof) =="
  META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh
  echo "== END PROVE_BASELINE_RATCHET =="
} | tee "$LOG" >/dev/null

echo "$(basename "$LOG")" > "$LATEST"
cleanup_old

echo "OK: baseline proof log=$LOG"
echo "OK: baseline latest -> $(cat "$LATEST")"

