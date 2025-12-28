#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
bash scripts/ops/verify_s7_always_on.sh

OUT_DIR="docs/ops"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG="$OUT_DIR/r10-s7-retriever-regression-proof-${TS}.log"
LATEST="$OUT_DIR/r10-s7-retriever-regression-proof.latest"

cleanup_old() {
  i=0
  for f in $(ls -1t "$OUT_DIR"/r10-s7-retriever-regression-proof-*.log 2>/dev/null || true); do
    i=$((i+1))
    if [ "$i" -gt 1 ]; then rm -f "$f"; fi
  done
}

{
  echo "== START PROVE_RETRIEVER_REGRESSION =="
  echo "TS=$TS"
  echo "PWD=$(pwd)"
  echo "== VERIFY REGRESSION GATE =="
  bash scripts/ops/verify_retriever_regression_gate.sh
  echo "== BASELINE (top 80) =="
  sed -n "1,80p" docs/ops/r10-s7-retriever-metrics-baseline.json || true
  echo "== REPORT (top 80) =="
  sed -n "1,80p" docs/ops/r10-s7-retriever-quality-phase1-report.json || true
      echo "== META_ONLY_DEBUG (scan list proof) =="
      DBG="$(META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh)"
      printf "%s\n" "$DBG"
      echo "$DBG" | grep -q "META_ONLY_DEBUG:" || { echo "FAIL: META_ONLY_DEBUG output missing"; exit 1; }
      echo "$DBG" | grep -q "docs/ops/r10-s7-retriever-metrics-baseline.json" || { echo "FAIL: baseline not shown in debug scan list"; exit 1; }
      echo "$DBG" | grep -q "docs/ops/r10-s7-retriever-quality-phase1-report.json" || { echo "FAIL: phase1 report not shown in debug scan list"; exit 1; }
      echo "$DBG" | grep -q "docs/ops/r10-s7-retriever-regression-proof.latest" || { echo "FAIL: regression latest not shown in debug scan list"; exit 1; }
      echo "$DBG" | grep -q "exclude docs/ops/r10-s7-retriever-corpus.jsonl" || { echo "FAIL: corpus exclusion not shown in debug output"; exit 1; }
      echo "== END PROVE_RETRIEVER_REGRESSION =="
} | tee "$LOG" >/dev/null

echo "$(basename "$LOG")" > "$LATEST"
cleanup_old

echo "OK: proof log=$LOG"
echo "OK: latest -> $(cat "$LATEST")"

