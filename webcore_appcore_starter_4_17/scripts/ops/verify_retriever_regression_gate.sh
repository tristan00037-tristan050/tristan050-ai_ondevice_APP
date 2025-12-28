#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
bash scripts/ops/verify_s7_always_on.sh

BASELINE="${BASELINE:-docs/ops/r10-s7-retriever-metrics-baseline.json}"
REPORT="${REPORT:-docs/ops/r10-s7-retriever-quality-phase1-report.json}"
TOL="${TOL:-0.0}"

test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }

bash scripts/ops/eval_retriever_quality_phase1.sh
test -f "$REPORT" || { echo "FAIL: phase1 report missing: $REPORT" >&2; exit 1; }

# 생성된 산출물이 meta-only 규칙을 계속 만족하는지(Always On 재검증)
bash scripts/ops/verify_s7_always_on.sh

python3 - <<'PY' "$BASELINE" "$REPORT" "$TOL"
import json, sys
baseline, report, tol = sys.argv[1], sys.argv[2], float(sys.argv[3])
b=json.load(open(baseline,"r",encoding="utf-8"))
r=json.load(open(report,"r",encoding="utf-8"))

# 입력 해시/알고리즘/TopK 불일치면 baseline 갱신 없이 비교 금지(결정적 차단)
if r.get("algo") != b.get("algo"):
    raise SystemExit(f"FAIL: algo mismatch baseline={b.get('algo')} current={r.get('algo')}")
if int(r.get("topk")) != int(b.get("topk")):
    raise SystemExit(f"FAIL: topk mismatch baseline={b.get('topk')} current={r.get('topk')}")
if r["inputs"]["goldenset_sha256"] != b["inputs"]["goldenset_sha256"]:
    raise SystemExit("FAIL: goldenset sha256 mismatch vs baseline (update baseline with proof)")
if r["inputs"]["corpus_sha256"] != b["inputs"]["corpus_sha256"]:
    raise SystemExit("FAIL: corpus sha256 mismatch vs baseline (update baseline with proof)")

keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
bad=[]
for k in keys:
    bv=float(b["metrics"][k])
    rv=float(r["metrics"][k])
    if rv + tol < bv:
        bad.append((k,bv,rv))

if bad:
    print("FAIL: retriever quality regression detected")
    for k,bv,rv in bad:
        print(f"- {k}: baseline={bv:.6f} current={rv:.6f} tol={tol}")
    raise SystemExit(1)

print("OK: no regression vs baseline")
PY

echo "OK: verify_retriever_regression_gate exit 0"

