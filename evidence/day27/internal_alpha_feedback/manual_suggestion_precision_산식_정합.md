# manual_suggestion_precision 산식 정합 (자문 5차 6.4)

## metadata
- source_pr: 733
- branch: Internal-Alpha-Feedback
- verdict: MEASURED_ONLY

## 산식

```
manual_suggestion_precision = accept / (accept + dismiss + irrelevant + unsafe)
```

- 분자: `accept` — manual suggestion 을 user 가 수동 채택한 건수.
- 분모: 4 카테고리 전체 (accept + dismiss + irrelevant + unsafe).
- 자문 5차 6.4 정합. Layer 2 보조 지표 (production gate 아님).

## Controlled Beta 진입 기준 (자문 5차 8.2)

`manual_suggestion_precision ≥ 0.80` + `auto_apply OFF`.

이 기준은 Controlled Beta 진입의 **정량 조건**이며, production candidate
gate(`strict_action_f1 ≥ 0.90`, Layer 1)와는 별개다. 두 기준은 평가 계약
v2.0.0 의 Layer 1 / Layer 2 분리 원칙에 따른다.

## 측정 방법

| option | 방법 | 본 PR |
|---|---|---|
| A | reviewer feedback (deterministic reviewer-simulation proxy) | 본진입 |
| B | synthetic pipeline 검증 | 본진입 (검증용) |
| C | 실제 Internal Alpha user feedback | 본 PR 범위 밖 |

## 측정 결과 (option A — simulation proxy)

manual_suggestion 후보 A3 32건:
- reviewer_strict: msp 0.4688
- reviewer_lenient: msp 0.6562
- Cohen's κ (strict vs lenient): 0.6735

두 값 모두 0.80 미만 — Controlled Beta msp gate 미충족.

## 정직 보고 (Standard 12)

msp 는 deterministic reviewer-simulation **proxy** 다. 실제 Internal Alpha
user feedback (option C)이 아니므로 권위 측정값이 아니다. Controlled Beta
진입의 정량 결정은 option C 실측 후 별도 Final Beta Readiness PR 에서
수행한다. 본 PR 은 측정 산식·인프라·proxy 측정을 정착한다.

reviewer 일관성 κ 0.6735 (< 0.7) — strict/lenient 분류 기준이 borderline
일관. 실제 human reviewer + PR #731 labeling guide 의 κ ≥ 0.7 검증은
option C 영역.
