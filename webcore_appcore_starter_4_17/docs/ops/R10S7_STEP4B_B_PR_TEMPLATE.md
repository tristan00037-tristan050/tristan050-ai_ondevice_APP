# S7 Step4-B B PR 템플릿 (정본)

## 목표
"입력 고정(데이터 변경 0)" 상태에서 **Regression Gate PASS + strict improvement(최소 1개 지표 baseline 초과)**를 증빙과 함께 남기는 PR.

## PR 기본 정보

- **Base(타깃)**: main
- **Compare(소스)**: feat/s7-step4b-b-algo-improve (권장 예시)
- **Title(정본)**: `feat(s7): step4-b-b enable tiebreak to achieve strict improvement (input frozen)`

## PR 본문 템플릿

```markdown
## 🎯 목적
Step4-B B(입력 고정 알고리즘 개선 PR):
- 입력(골든셋/코퍼스) 변경 없이
- Regression Gate PASS를 유지하면서
- strict improvement(최소 1개 지표 baseline 초과)을 달성합니다.

## 🔒 변수 통제(필수, 실험설계)
- [ ] Input Frozen: `docs/ops/r10-s7-retriever-goldenset.jsonl` 변경 0
- [ ] Input Frozen: `docs/ops/r10-s7-retriever-corpus.jsonl` 변경 0
- [ ] Baseline Frozen: `docs/ops/r10-s7-retriever-metrics-baseline.json` 변경 0
- [ ] Mixed PR 금지: 입력 변경 + 알고리즘 변경 혼합 없음(입력 변경 0)

## ✅ 로컬 증빙(메타-only)
### 1) Always On / Input Safety
- `bash scripts/ops/verify_s7_always_on.sh` : PASS
- `bash scripts/ops/verify_s7_corpus_no_pii.sh` : PASS (입력 변경은 없으나 안전 확인)

### 2) Regression Gate (must PASS)
- `bash scripts/ops/prove_retriever_regression_gate.sh` : PASS
- proof 최신: `docs/ops/r10-s7-retriever-regression-proof.latest` 갱신됨

### 3) Meta-only
- `bash scripts/ops/verify_rag_meta_only.sh` : PASS
- proof 내 `== META_ONLY_DEBUG (scan list proof) ==` 섹션 존재(스캔/제외 문자열 증거)

## 📈 strict improvement 증빙(필수)
Baseline vs Current (Phase1 report):
- baseline: `docs/ops/r10-s7-retriever-metrics-baseline.json`
- report: `docs/ops/r10-s7-retriever-quality-phase1-report.json`
- improved metrics: <FILL_ME: 예: mrr_at_k, ndcg_at_k ...>
- delta: <FILL_ME: +0.00xxxx>

(증빙 출력 로그/스크린샷 링크 또는 콘솔 출력 첨부)

## 🧪 CI 기대 동작
- input_changed=0 → Regression Gate가 반드시 실행되고 PASS
- baseline 변경 감지 스텝: PASS(= baseline 변경 0)
- mixed PR 차단 스텝: PASS(= 혼합 아님)
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

