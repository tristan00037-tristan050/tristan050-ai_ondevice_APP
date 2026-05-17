# Layer 2 Classification Contract Specification

## metadata
- source_pr: 731
- branch: Metric-Design-Review
- correction_cycle: Codex P1 (A5 분류 계약 정정)
- verdict: MEASURED_ONLY

## 목적

`classify_layer2()` 의 분류 계약을 gold/pred action count 매트릭스로
명세한다. Codex P1 정정 — A5 는 gold≥1 AND pred≥1 일 때만 성립하며,
gold≥1/pred=0 은 false negative (A7) 로 정직 분리한다.

## gold/pred 매트릭스

| gold_action_count | pred_action_count | subtype | 의미 |
|---|---|---|---|
| 0 | 0 | `no_action` | MIXED-A 영역 아님 |
| 0 | ≥1, intent=QUESTION | `A3_product_equivalent_prediction` | over-extraction, 사용자 가치 有 |
| 0 | ≥1, intent≠QUESTION | `A4_true_over_extraction_error` | over-extraction, 불필요/위험 |
| ≥1 | ≥1 | `A5_metric_contract_gap` | canonicalization 차이 false mismatch |
| ≥1 | 0 | `A7_false_negative` | action 누락 (recall 결함) |

`A6_unresolved_user_value` 는 결정적 규칙으로 산출되지 않는 reserved 범주
— Internal Alpha reviewer feedback 이 채운다.

## subtype 정의

- **A3 product_equivalent_prediction** — gold=0/pred≥1, gold_intent=QUESTION.
  pred 가 사용자가 원할 행동을 추출. manual suggestion 후보 (auto_apply OFF).
- **A4 true_over_extraction_error** — gold=0/pred≥1, gold_intent≠QUESTION.
  보고/완료 진술에서 action 오추출. dangerous_over_extraction_guard 대상.
- **A5 metric_contract_gap** — gold≥1 AND pred≥1. gold·pred 모두 action
  보유, canonicalization 차이로 strict matching 실패. 계약 정의상 false
  mismatch.
- **A6 unresolved_user_value** — 결정적 규칙 미해결, Alpha feedback reserved.
- **A7 false_negative** — gold≥1 AND pred=0. action 누락 — recall 축 결함.
  strict layer 의 FN 으로 이미 반영되며, recall 보강은 별도 PR 안건.

## Codex P1 정정 본질

이전 `classify_layer2()` 는 `if gold_action_count >= 1: return A5` 로
pred_action_count 를 검사하지 않았다. gold≥1/pred=0 (false negative) 까지
A5 (metric_contract_gap) 로 오분류하는 분류 계약 결함이었다. 정정 후 A5 는
gold≥1 AND pred≥1 일 때만 성립하고, gold≥1/pred=0 은 A7 로 정직 분리.

## sentinel 정합 보증

- `#9 test_A5_requires_gold_and_pred` — gold≥1 AND pred≥1 → A5.
- `#10 test_A5_excludes_gold_only` — gold≥1/pred=0 → A7 (≠ A5),
  gold=0/pred=0 → no_action.
- `#11 test_evidence_metadata_deterministic` — _meta() 결정적.

## 데이터 영향 (정직 보고)

MIXED-A 67건에는 gold≥1/pred=0 케이스가 0건이다 (MIXED-A 정의상 pred≥1).
따라서 A7=0, A3/A4/A5/A6 분포는 정정 전후 불변. P1 은 분류 계약의
정밀화이며 측정값 임의 조정이 아니다.

## metric contract version

P1/P2 정정은 분류 계약 정밀화 + evidence 재현성 정정이며, metric contract
version (v2.0.0) 의 추가 bump 사유가 아니다. v2.0.0 유지.
