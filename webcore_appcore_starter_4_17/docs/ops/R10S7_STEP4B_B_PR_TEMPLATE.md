# S7 Step4-B B PR 템플릿 (정본)

## 목표
"입력 고정(데이터 변경 0)" 상태에서 **Regression Gate PASS + strict improvement(최소 1개 지표 baseline 초과)**를 증빙과 함께 남기는 PR.

## PR 기본 정보

- **Base(타깃)**: main
- **Compare(소스)**: feat/s7-step4b-b-algo-improve (권장 예시)
- **Title(정본)**: `feat(s7): step4-b b algorithm improvement with strict metric gain (input frozen)`

## PR 본문 템플릿

```markdown
## 목적
Step4-B B(입력 고정 알고리즘 개선 PR)에서 **Regression Gate PASS**를 유지하면서
**strict improvement ≥ 1(최소 1개 지표 baseline 초과)**를 달성한다.

## 변수 통제(필수)
- [ ] Input Frozen: `docs/ops/r10-s7-retriever-goldenset.jsonl` 변경 0
- [ ] Input Frozen: `docs/ops/r10-s7-retriever-corpus.jsonl` 변경 0
- [ ] Baseline Frozen: `docs/ops/r10-s7-retriever-metrics-baseline.json` 변경 0
- [ ] Mixed PR 금지 준수(입력 변경 없음)

## 실행/게이트 결과(증빙)
- Always On: PASS (`bash scripts/ops/verify_s7_always_on.sh`)
- Corpus PII Gate: PASS (`bash scripts/ops/verify_s7_corpus_no_pii.sh`)
- Regression Gate: PASS (`bash scripts/ops/prove_retriever_regression_gate.sh`)
- Meta-only: PASS (`META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh`)
- Proof SSOT:
  - `docs/ops/r10-s7-retriever-regression-proof.latest` 갱신
  - Proof log 내 `== META_ONLY_DEBUG (scan list proof) ==` 존재

## Strict Improvement(정본 포맷)
(Phase1 report vs baseline, 최소 1개 지표 strictly greater)

아래 JSON은 실행 결과로 채워 넣습니다(메타 only).

```json
{
  "baseline_sha": "<baseline file sha or commit sha>",
  "report_path": "docs/ops/r10-s7-retriever-quality-phase1-report.json",
  "improved_keys": ["mrr_at_k"],
  "metrics": {
    "precision_at_k": {"baseline": 0.000000, "current": 0.000000, "delta": "+0.000000"},
    "recall_at_k":    {"baseline": 0.000000, "current": 0.000000, "delta": "+0.000000"},
    "mrr_at_k":       {"baseline": 0.000000, "current": 0.000000, "delta": "+0.000000"},
    "ndcg_at_k":      {"baseline": 0.000000, "current": 0.000000, "delta": "+0.000000"}
  }
}
```

## 중요 규칙

- `--reanchor-input`는 입력 변경 A 전용이며, Step4-B B(입력 고정)에서는 사용하지 않는다.
- baseline 갱신은 PR에서 금지, merge 후 main에서 ratchet로만 수행한다.
```

## strict improvement 증빙 표준 포맷

### (A) 콘솔 출력 표준(권장)
```
[Strict Improvement Evidence]
baseline: docs/ops/r10-s7-retriever-metrics-baseline.json
report:   docs/ops/r10-s7-retriever-quality-phase1-report.json

precision_at_k: baseline=0.xxxxxx current=0.xxxxxx delta=+0.xxxxxx
recall_at_k:    baseline=0.xxxxxx current=0.xxxxxx delta=+0.xxxxxx
mrr_at_k:       baseline=0.xxxxxx current=0.xxxxxx delta=+0.xxxxxx
ndcg_at_k:      baseline=0.xxxxxx current=0.xxxxxx delta=+0.xxxxxx

IMPROVED_KEYS=[mrr_at_k]   # 최소 1개 이상이어야 함
proof.latest=docs/ops/r10-s7-retriever-regression-proof.latest
meta-only=PASS (verify_rag_meta_only.sh)
```

### (B) JSON 표준(자동화/아카이빙 용)
```json
{
  "strict_improvement": true,
  "baseline_path": "docs/ops/r10-s7-retriever-metrics-baseline.json",
  "report_path": "docs/ops/r10-s7-retriever-quality-phase1-report.json",
  "improved_keys": ["mrr_at_k"],
  "metrics": {
    "precision_at_k": {"baseline": 0.0, "current": 0.0, "delta": 0.0},
    "recall_at_k":    {"baseline": 0.0, "current": 0.0, "delta": 0.0},
    "mrr_at_k":       {"baseline": 0.0, "current": 0.0, "delta": 0.0},
    "ndcg_at_k":      {"baseline": 0.0, "current": 0.0, "delta": 0.0}
  },
  "proof_latest": "docs/ops/r10-s7-retriever-regression-proof.latest",
  "meta_only": true
}
```

