#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh

BASELINE="${BASELINE:-docs/ops/r10-s7-retriever-metrics-baseline.json}"
REPORT="${REPORT:-docs/ops/r10-s7-retriever-quality-phase1-report.json}"

TOL="${TOL:-0.0}"

UPDATE=0
MIN_GAIN=0.0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --update-baseline)
      UPDATE=1
      shift
      ;;
    --min-gain)
      MIN_GAIN="$2"
      shift 2
      ;;
    *)
      echo "FAIL: unknown option: $1" >&2
      echo "Usage: $0 [--update-baseline] [--min-gain VALUE]" >&2
      exit 1
      ;;
  esac
done

# Phase1 report 생성(현 러너 기준)
bash scripts/ops/eval_retriever_quality_phase1.sh
test -f "$REPORT"

if [ "$UPDATE" -ne 1 ]; then
  echo "OK: baseline update skipped (require --update-baseline)"
  exit 0
fi

test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }

python3 - <<'PY' "$BASELINE" "$REPORT" "$TOL" "$MIN_GAIN"
import json, sys
base, rep, tol, min_gain = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
b=json.load(open(base,"r",encoding="utf-8"))
r=json.load(open(rep,"r",encoding="utf-8"))

# 입력 동일성 강제(라쳇 안정성)
if r["inputs"]["goldenset_sha256"] != b["inputs"]["goldenset_sha256"]:
    raise SystemExit("FAIL: goldenset sha256 mismatch vs baseline (input change requires separate procedure)")
if r["inputs"]["corpus_sha256"] != b["inputs"]["corpus_sha256"]:
    raise SystemExit("FAIL: corpus sha256 mismatch vs baseline (input change requires separate procedure)")

keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]

decrease=[]
improve=False
for k in keys:
    bv=float(b["metrics"][k])
    rv=float(r["metrics"][k])
    if rv + tol < bv:
        decrease.append((k,bv,rv))
    if rv > bv + min_gain:
        improve=True

if decrease:
    print("FAIL: cannot ratchet baseline (regression detected)")
    for k,bv,rv in decrease:
        print(f"- {k}: baseline={bv:.6f} current={rv:.6f} tol={tol}")
    raise SystemExit(1)

if not improve and min_gain > 0.0:
    raise SystemExit(f"FAIL: no metric improved by MIN_GAIN={min_gain}")

print("OK: ratchet conditions satisfied (no decreases; improvement requirement met if configured)")
PY

# baseline 교체(meta-only)
python3 - <<'PY' "$REPORT" "$BASELINE"
import json, sys, time
rep, base = sys.argv[1], sys.argv[2]
r=json.load(open(rep,"r",encoding="utf-8"))
b={
  "ok": True,
  "phase": "S7/Phase1Baseline",
  "meta_only": True,
  "topk": r["topk"],
  "inputs": {
    "goldenset_sha256": r["inputs"]["goldenset_sha256"],
    "corpus_sha256": r["inputs"]["corpus_sha256"]
  },
  "metrics": r["metrics"],
  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}
open(base,"w",encoding="utf-8").write(json.dumps(b, ensure_ascii=False, indent=2) + "\n")
print(f"OK: baseline ratcheted: {base}")
PY

# meta-only 스캔 + DEBUG 출력(레포 증빙용)
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh >/dev/null
echo "OK: update_retriever_baseline completed"

