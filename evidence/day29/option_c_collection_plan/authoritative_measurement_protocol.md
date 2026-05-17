# Authoritative Measurement Protocol (자문 6차 §6/§9/§11)

## metadata
- source_pr: 737
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## proxy vs 권위 측정 (Standard 12-H)

| 구분 | proxy (PR #733) | 권위 측정 (option C, 본 계획) |
|---|---|---|
| 출처 | deterministic reviewer-simulation | 실제 Internal Alpha user feedback |
| msp | strict 0.4688 / lenient 0.6562 | 미측정 (배포 후) |
| Cohen's κ | 0.6735 (marginal 미달) | 미측정 (목표 ≥ 0.70) |
| Controlled Beta 판정 | **사용 불가** (자문 6차 M-10) | 사용 |

proxy 측정은 Controlled Beta 진입 판정에 사용할 수 없다 (자문 6차 M-10).
권위 측정만이 진입 정량 결정의 근거다.

## msp 권위 측정 산식

```
manual_suggestion_precision = useful / (useful + irrelevant + unsafe + needs_edit)
```

PR #733 산식과 정합 (카테고리만 4종으로 확정 — useful 이 accept 대응).
sample size 는 최소 100 / 권장 150 (`minimum_sample_size_정량.json`).

## Cohen's κ 권위 측정 + 개선 (자문 6차 §9)

- reviewer 최소 2명 (+adjudicator) / 권장 3명 — `reviewer_guide.md`.
- 10건 calibration round 후 κ 측정.
- κ < 0.70 시 reviewer guide 재정의 + disagreement adjudication →
  재측정 (`cohens_kappa_improvement_protocol.md`).
- 목표 κ ≥ 0.70 (자문 6차 M-11).

## Controlled Beta 진입 정량 결정 (자문 6차 §11)

권위 측정 완료 후 `controlled_beta_8조건_정량.json` 의 8 조건을 모두
정량 평가한다. 8 조건 모두 충족 시에만 진입 정량 결정 (별도 판정 PR).
proxy → 권위 측정 비교를 정직 보고한다 (Standard 12-H).

## 정직 보고 (Standard 12)

본 PR 은 protocol 만 정착한다. 권위 측정값은 정식 Internal Alpha 배포
후에만 산출 가능하며, 본 PR 시점에 msp/κ 권위 값은 존재하지 않는다 —
이를 정직 보고한다.
