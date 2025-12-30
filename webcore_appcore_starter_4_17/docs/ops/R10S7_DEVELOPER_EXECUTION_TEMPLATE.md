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

# 입력 고정 확인(변경 0이어야 함)
git fetch origin main --depth=1
CHANGED="$(git diff --name-only origin/main...HEAD)"
echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$" && {
  echo "FAIL: input must be frozen in Step4-B B"
  exit 1
} || true

echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-metrics-baseline\.json$" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

bash scripts/ops/prove_retriever_regression_gate.sh
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh

# strict improvement 확인(최소 1개 지표 baseline 초과)
python3 - <<'PY'
import json
b=json.load(open("docs/ops/r10-s7-retriever-metrics-baseline.json","r",encoding="utf-8"))
r=json.load(open("docs/ops/r10-s7-retriever-quality-phase1-report.json","r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]

improved=[]
print("=== STRICT IMPROVEMENT CHECK (meta-only) ===")
for k in keys:
    bv=float(b["metrics"][k])
    rv=float(r["metrics"][k])
    print(f"{k}: baseline={bv:.6f} current={rv:.6f} delta={rv-bv:+.6f}")
    if rv>bv:
        improved.append(k)

print("IMPROVED_KEYS=", improved)
raise SystemExit(0 if improved else 1)
PY
```

## merge 후 main에서 baseline 상향 (ratchet, 입력 고정)

Step4-B B는 **입력 고정 상태의 "성능 개선"**이므로, merge 후 main에서 re-anchoring이 아니라 ratchet로 올립니다.

**입력이 변하지 않았으면 `--reanchor-input`을 쓰지 않습니다.**

```bash
# main에서만
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

**주의사항**:
- `--min-gain`은 팀 기준값으로 운용 (예: 0.001 또는 0.005 등)
- 입력 해시가 동일하므로 `--reanchor-input` 옵션 불필요

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

