# S7 개발팀 실행 템플릿 (정본)

## 입력 변경 PR(데이터 확장 PR)

```bash
bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh
bash scripts/ops/eval_retriever_quality_phase1.sh
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh
```

## merge 후 main re-anchoring(정본)

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.00
bash scripts/ops/verify_retriever_regression_gate.sh
```

## 입력 고정 PR(알고리즘 개선 PR)

```bash
bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/prove_retriever_regression_gate.sh
bash scripts/ops/verify_rag_meta_only.sh
# + strict improvement 비교(Python) 결과를 PR에 증빙으로 남김
```

## strict improvement 체크 스크립트

```bash
python3 - <<'PY'
import json
base="docs/ops/r10-s7-retriever-metrics-baseline.json"
rep ="docs/ops/r10-s7-retriever-quality-phase1-report.json"
b=json.load(open(base,"r",encoding="utf-8"))
r=json.load(open(rep ,"r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]

improved=[]
print("=== STRICT IMPROVEMENT CHECK (meta-only numbers) ===")
for k in keys:
    bv=float(b["metrics"][k])
    rv=float(r["metrics"][k])
    d=rv-bv
    print(f"{k}: baseline={bv:.6f} current={rv:.6f} delta={d:+.6f}")
    if rv>bv:
        improved.append(k)

print("IMPROVED_KEYS=", improved)
raise SystemExit(0 if improved else 1)
PY
```

