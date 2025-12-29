#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh

BASELINE="${BASELINE:-docs/ops/r10-s7-retriever-metrics-baseline.json}"
test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }

# 후보: min_primary 1~3
for MP in 1 2 3; do
  REP="/tmp/s7_phase1_tune_mp${MP}.json"
  TIEBREAK_ENABLE=1 TIEBREAK_MIN_PRIMARY="$MP" REPORT="$REP" bash scripts/ops/eval_retriever_quality_phase1.sh >/dev/null

  python3 - <<'PY' "$BASELINE" "$REP" "$MP"
import json, sys
base, rep, mp = sys.argv[1], sys.argv[2], sys.argv[3]
b=json.load(open(base,"r",encoding="utf-8"))
r=json.load(open(rep,"r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
dec=[]
inc=[]
for k in keys:
    bv=float(b["metrics"][k]); rv=float(r["metrics"][k])
    d=rv-bv
    if d < 0: dec.append((k,d))
    if d > 0: inc.append((k,d))
# meta-only 출력(수치만)
status="OK" if not dec else "BAD"
deltas = ",".join([f"{k}:{float(r['metrics'][k])-float(b['metrics'][k]):+.6f}" for k in keys])
print(f"{status}: tiebreak_min_primary={mp} deltas={deltas}")
PY
done

echo "OK: tune_retriever_tiebreak done (meta-only)"

