# Cohen's κ Improvement Protocol (자문 6차 §9)

## metadata
- source_pr: 737
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## 현 상태 정직 보고

PR #733 proxy κ = **0.6735** — 목표 0.70 marginal 미달. strict/lenient
reviewer-simulation 의 분류 기준이 borderline 일관. 권위 측정에서 human
reviewer 의 κ ≥ 0.70 을 확보해야 한다 (자문 6차 M-11).

## 개선 절차

1. **reviewer guide 강화** — `reviewer_guide.md` 의 4 카테고리(useful /
   irrelevant / unsafe / needs_edit) 정의를 명확화. 경계 사례 예시 포함.
2. **10건 calibration round** — reviewer 전원 독립 평가 → 해석 차이 식별
   → guide 보강.
3. **disagreement adjudication** — 불일치 sample 을 adjudicator 가 조정,
   조정 사유를 기록.
4. **κ 재측정** — calibration + adjudication 후 본 평가에서 κ 측정.
   목표 ≥ 0.70.
5. κ < 0.70 시 — 카테고리 정의를 재정의하고 calibration round 를 재수행.

## κ 산식

Cohen's κ = (po − pe) / (1 − pe). po = 관측 일치율, pe = 우연 일치율.
PR #733 `cohens_kappa()` helper 정합 (산식 변경 없음).

## 정직 보고

본 PR 은 개선 protocol 만 정착한다. 권위 κ 값은 정식 Internal Alpha
배포 후 human reviewer 평가에서만 산출된다 — proxy κ 0.6735 을 권위
값으로 사용하지 않는다 (Standard 12-H).
