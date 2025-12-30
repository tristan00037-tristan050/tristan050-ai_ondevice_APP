## 목적
본 PR은 **S7 Step4-B B(입력 고정 알고리즘 개선 PR)** 입니다.  
입력(goldenset/corpus) 변경 없이, **Regression Gate PASS**를 유지하면서
**strict improvement(최소 1개 지표 baseline 초과)**를 달성하고,
증빙(**proof/.latest + META_ONLY_DEBUG**)을 남깁니다.

---

## 변수 통제(정본)
- 입력 고정: `docs/ops/r10-s7-retriever-goldenset.jsonl` 변경 0
- 입력 고정: `docs/ops/r10-s7-retriever-corpus.jsonl` 변경 0
- baseline 파일 PR 변경 0: `docs/ops/r10-s7-retriever-metrics-baseline.json` 변경 0
- 혼합 PR 금지 준수: 입력 변경(A)과 혼합 금지

---

## 금지(정본)
- PR에서 baseline 변경 금지(0)
- 입력 변경(A)과 알고리즘 변경 혼합 금지
- Step4-B B에서는 `--reanchor-input` 사용 금지(입력 고정이므로 불필요)

---

## 하드 게이트(merge 조건, 정본)
- Always On PASS (`bash scripts/ops/verify_s7_always_on.sh`)
- Regression Gate PASS (로컬 + CI)
- meta-only PASS + proof log에 `== META_ONLY_DEBUG (scan list proof) ==` 증거 포함
- strict improvement ≥ 1 (정본 JSON 증빙)
- proof/.latest 갱신 유지

---

## 로컬 원샷 실행(정본) + Strict Improvement JSON(증빙)
아래 블록을 실행해 결과(JSON)를 그대로 PR에 첨부합니다.

```bash
bash -lc '
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
APP="$ROOT/webcore_appcore_starter_4_17"

# Always On
cd "$APP"
bash scripts/ops/verify_s7_always_on.sh

# 입력 고정 확인(변경 0이어야 함)
cd "$ROOT"
git fetch origin main --depth=1
CHANGED="$(git diff --name-only origin/main...HEAD)"
echo "$CHANGED" | sed -n "1,200p"

echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$" && {
  echo "FAIL: input must be frozen for Step4-B B"
  exit 1
} || true

echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-metrics-baseline\.json$" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

# Regression Gate + proof/.latest (must PASS)
cd "$APP"
export TIEBREAK_ENABLE=1
bash scripts/ops/prove_retriever_regression_gate.sh

# meta-only debug evidence
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh | tee /tmp/meta_only_debug_step4b_b.log

# strict improvement JSON (Phase1 report vs baseline)
python3 - <<'"'"'PY'"'"'
import json
b=json.load(open("docs/ops/r10-s7-retriever-metrics-baseline.json","r",encoding="utf-8"))
r=json.load(open("docs/ops/r10-s7-retriever-quality-phase1-report.json","r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
improved=[k for k in keys if float(r["metrics"][k])>float(b["metrics"][k])]

out={
  "step": "S7 Step4-B B",
  "input_fixed": True,
  "regression_gate": "PASS",
  "strict_improvement": True if improved else False,
  "improved_metrics": improved,
  "baseline_metrics": b["metrics"],
  "current_metrics": r["metrics"]
}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if improved else 1)
PY
'
```

## CI 확인 포인트(정본)

- 입력 변경이 없으므로(input_changed=0) Regression Gate는 반드시 실행되고 PASS해야 합니다.
- Data Expansion Gate 분기로 들어가면 안 됩니다(입력 고정 PR).
- meta-only PASS 및 로그/증빙에 META_ONLY_DEBUG scan/exclude 증거가 남아야 합니다.

## merge 후 main baseline ratchet(정본)

본 PR에서는 baseline 파일 변경이 없습니다.
merge 후 main에서만 baseline ratchet를 수행합니다. (B안이므로 --reanchor-input 사용 금지)

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.001
```

## PASS 선언 금지 조건(정본)

입력 고정 증거(변경 0), Regression Gate PASS(로컬/CI), meta-only + META_ONLY_DEBUG 증거,
strict improvement JSON(최소 1개 지표 baseline 초과) 4개가 모두 없으면 PASS 선언 금지입니다.

