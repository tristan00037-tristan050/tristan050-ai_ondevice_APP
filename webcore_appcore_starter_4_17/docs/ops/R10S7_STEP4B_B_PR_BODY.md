## 목적
본 PR은 **S7 Step4-B B(입력 고정 알고리즘 개선 PR)** 입니다.  
입력(goldenset/corpus) 변경 없이, **Regression Gate PASS(로컬+CI)**를 유지하면서  
**strict improvement(최소 1개 지표 baseline 초과)**를 달성하고, meta-only/증빙(proof/.latest + META_ONLY_DEBUG)을 남깁니다.

---

## SSOT(정본 파일: 본 PR의 "규칙/템플릿/원샷" 기준)
- PR 본문 정본: `docs/ops/R10S7_STEP4B_B_PR_BODY.md`
- PR 템플릿: `docs/ops/R10S7_STEP4B_B_PR_TEMPLATE.md`
- Cursor 원샷 프롬프트: `docs/ops/R10S7_STEP4B_B_CURSOR_PROMPT.md`
- 로컬 원샷 실행 스크립트: `docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh`

본 PR의 실행/증빙/판정은 위 SSOT에 정의된 규칙을 그대로 따릅니다.

---

## 하드룰(Non-negotiable)
- 입력 고정(변경 0):
  - `docs/ops/r10-s7-retriever-goldenset.jsonl` 변경 0
  - `docs/ops/r10-s7-retriever-corpus.jsonl` 변경 0
- baseline PR 변경 0:
  - `docs/ops/r10-s7-retriever-metrics-baseline.json` 변경 0
- Regression Gate PASS(로컬+CI) 없으면 merge 불가
- strict improvement ≥ 1(JSON 정본 증빙 필수)
- Always On/meta-only PASS + proof/.latest + META_ONLY_DEBUG 증빙 유지
- Step4-B B에서 `--reanchor-input` 사용 금지(A 전용)

---

## 로컬 실행(정본)
로컬에서는 아래 정본 원샷 스크립트를 사용하여 실행/증빙을 남깁니다.

```bash
bash docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh
```

### Strict Improvement 증빙(JSON 정본)

원샷 스크립트 출력(또는 SSOT에 정의된 비교 스크립트 출력)에서
`strict_improvement=true`이며 `improved_metrics`가 비어있지 않음을 증빙으로 첨부합니다.

```json
<PASTE_STRICT_IMPROVEMENT_JSON_HERE>
```

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

