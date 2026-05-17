# Manual Suggestion Labeling Guide (Internal Alpha)

## metadata
- source_pr: 731
- branch: Metric-Design-Review
- verdict: MEASURED_ONLY

## 목적

Internal Alpha reviewer 가 gold=0/pred≥1 over-extraction 케이스를 Layer 2
4 subtype 으로 일관되게 분류하기 위한 가이드. 본 분류는 manual suggestion
UX 판단용이며, gold label 을 수정하지 않는다.

## A3 — product_equivalent_prediction

판단 기준:
- 원문이 정보/행동 요청 성격 (gold_intent = QUESTION).
- pred action 이 사용자가 실제로 원할 법한 행동을 표현.
- 자동 실행은 부적절하나, **수동 제안으로 보여주면 가치 있음**.
- route: `manual_suggestion_candidate` (auto_apply OFF).

예: "버전 정보 알 수 있을까요?" → pred "버전 정보 확인" — 질문이지만
사용자는 버전 정보를 원함 → 수동 제안 후보.

## A4 — true_over_extraction_error

판단 기준:
- 원문이 보고/완료 진술 (gold_intent = REPORT / NO_ACTION 등).
- pred 가 action 을 추출했으나 사용자는 행동을 요청하지 않음.
- 수동 제안으로도 부적절 — 불필요하거나 위험.
- route: `dangerous_over_extraction_guard` 후보.

예: "회의 결과 정리되면 알려드리겠습니다" → pred "회의 결과 정리" —
완료 예고 보고이지 행동 요청 아님 → over-extraction guard 대상.

## A5 — metric_contract_gap

판단 기준:
- gold 와 pred 모두 action 을 보유 (gold≥1).
- 계약 정의상 MIXED-A mismatch 로 집계되나, 단위/표현 차이일 뿐
  양쪽 모두 타당할 수 있음.
- route: 평가 계약(contract) review — gold 수정 아님.

## A6 — unresolved_user_value

판단 기준:
- A3/A4/A5 결정적 규칙으로 판정 불가한 모호 케이스.
- reviewer 가 원문만으로 사용자 가치를 확정할 수 없음.
- route: Internal Alpha user feedback 으로 확정 (`alpha_feedback_schema`).

## reviewer 일관성

- 동일 케이스에 대한 reviewer 간 일관성 Cohen's κ ≥ 0.7 권고.
- κ < 0.7 인 subtype 은 판단 기준을 재정의 후 재라벨링.
- 분류는 manual suggestion UX 판단 전용 — gold / normalized_action label
  은 어떤 경우에도 수정하지 않는다.
