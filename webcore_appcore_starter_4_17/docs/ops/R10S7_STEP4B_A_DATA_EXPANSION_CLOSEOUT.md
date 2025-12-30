# [Closeout] R10-S7 Step4-B A — Data Expansion PR (Input Change) CLOSED & SEALED

## 1. Summary
- **Status:** **CLOSED & SEALED**
- **Scope:** S7 Step4-B **A안(동점 분해 데이터 보강)** — 입력 변경 PR 절차 정본 봉인
- **Key Result:** 입력 변경 PR이 Phase 1 Regression Gate(기존 baseline 비교)를 우회하는 구멍이 되지 않도록, **CI 분기/차단/증빙**이 결정적으로 고정되었고, merge 후 main에서 baseline **re-anchoring(ratchet)** 까지 봉인 완료.

---

## 2. Canonical Procedure (Must Split, No Mixing)

### A) Data Expansion PR (Input Change PR)
**Purpose:** goldenset/corpus 확장(동점 분해 케이스 주입)

**Why split is mandatory:** 입력 해시가 변경되므로, 기존 baseline과 Phase 1 Regression 비교를 PASS 기대(통과 기대)로 운영하면 안 됨.

**Hard Gates (merge 조건, canonical):**
- `bash scripts/ops/verify_s7_always_on.sh` PASS
- `bash scripts/ops/verify_s7_corpus_no_pii.sh` PASS
- Phase 1 report 생성 PASS (metan (canonical):**
- Phase 1 Regression Gate(기존 baseline 비교)를 PASS 기준으로 요구 금지
- FAIL을 정상으로 기록 금지
- baseline 파일 수정 금지(PR에서 0)

### Merge 후 main에서 해야 하는 것 (Re-anchoring, canonical)
입력 변경은 기준 재정렬이므로 **min-gain 0 허용**.

```bash
bash scripts/ops/prove_update_retriever_baseline.sh --update-baseline --min-gain 0.00
```
