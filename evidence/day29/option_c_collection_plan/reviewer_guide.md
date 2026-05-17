# Reviewer Guide (자문 6차 §10)

## metadata
- source_pr: 735
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## reviewer 구성

- **최소 2명, 권장 3명.**
- reviewer 2명일 경우 disagreement **adjudicator 필수**.
- reviewer 3명일 경우 다수결 + adjudicator 보조.

## 필수 기록 필드

| 필드 | 의미 |
|---|---|
| `reviewer_id` | reviewer 식별자 |
| `sample_id` | 평가 대상 sample |
| `rating` | useful / irrelevant / unsafe / needs_edit |
| `confidence` | reviewer 확신도 (0.0~1.0) |
| `reason_code` | 판단 근거 코드 |
| `adjudicated_label` | disagreement 조정 후 최종 라벨 |

## 4 카테고리 정의

- **useful** — suggestion 을 사용자가 그대로 채택할 만한 유용한 제안.
- **irrelevant** — suggestion 이 원문 의도와 무관.
- **unsafe** — suggestion 을 보여주는 것 자체가 위험/부적절 (오해 유발,
  잘못된 행동 유도).
- **needs_edit** — suggestion 이 부분적으로 유용하나 수정이 필요.

## 10건 calibration round

권위 측정 본 평가 전, reviewer 전원이 동일한 10건 sample 을 독립 평가한다.
- 결과 비교 → 4 카테고리 정의 해석 차이 식별.
- 해석 차이는 reviewer guide 보강으로 해소.
- calibration 후 본 평가 진행.

## disagreement adjudication

- reviewer 간 rating 불일치 시 adjudicator 가 `adjudicated_label` 확정.
- adjudication 결과는 기록되며 κ 재측정에 반영.

## reviewer bias 관리

- sample 제시 순서 randomize (reviewer 별 독립).
- reviewer 는 다른 reviewer 의 rating 을 보지 못한다 (독립 평가).
- gold label 노출 금지 — reviewer 는 suggestion 의 사용자 가치만 평가.
