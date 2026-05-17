# Strict vs Suggestion Metric Contract (자문 5차 4.2)

## metadata
- source_pr: 731
- branch: Metric-Design-Review
- contract_version: 1.0.0 → 2.0.0
- verdict: MEASURED_ONLY

## 목적

MIXED-A 분석(PR #730)에서 gold=0/pred≥1 over-extraction 케이스의 76.7%
(30건 sample) / 47.8%(67건 전체)가 사용자 관점에서 가치 있는 예측으로
나타났다. 그러나 strict extraction 기준에서는 모두 FP 다. 단일 지표로는
production 안전성(strict)과 manual suggestion 가치(UX)를 동시에 표현할 수
없다. 이에 평가 계약을 2 Layer 로 분리한다.

## Layer 1 — Strict Extraction (production candidate gate)

- `strict_action_f1` = 기존 `normalized_action_f1` **그대로 유지** (산식 변경 없음).
- gold=0/pred≥1 → **FP** (기존 유지 — FP→TP 임의 처리 금지).
- production candidate gate: `strict_action_f1 ≥ 0.90`.
- 현재 실측: `strict_action_f1 = 0.6182` (gate 미달 — 기존과 동일).
- Layer 1 은 자동 실행(auto_apply) 가능 여부를 판정하는 유일한 gate.

## Layer 2 — Manual Suggestion Value (Internal Alpha / UX)

gold=0/pred≥1 케이스를 사용자 가치 기준으로 4 분류:

| subtype | 의미 | route |
|---|---|---|
| A3 product_equivalent_prediction | gold_intent=QUESTION, pred 가 정보/행동 요청 추출 | manual_suggestion_candidate |
| A4 true_over_extraction_error | gold_intent≠QUESTION (보고/완료 진술) | dangerous_over_extraction_guard |
| A5 metric_contract_gap | gold≥1 — gold·pred 모두 action, 계약 정의상 mismatch | contract review |
| A6 unresolved_user_value | 결정적 규칙 미해결 | Internal Alpha feedback |

- Layer 2 는 **수동 제안(manual suggestion) 전용** — `auto_apply` 는 OFF 유지.
- Layer 2 만으로는 production candidate gate 를 통과할 수 없다 (Layer 1
  strict gate 가 유일 판정).

## 보조 지표 (Layer 2)

| 지표 | 정의 | 산식 |
|---|---|---|
| `product_equivalent_action_rate` | over-extraction 중 사용자 가치 있는 비율 | A3 / (A3+A4+A5+A6) |
| `dangerous_over_extraction_rate` | over-extraction 중 불필요/위험 비율 | A4 / (A3+A4+A5+A6) |
| `manual_suggestion_precision` | 수동 제안으로 보일 때 유효 비율 | A3 정합 / (A3+A4) — Alpha feedback 후 측정 |
| `strict_action_f1` | Layer 1 — 기존 normalized_action_f1 | 변경 없음 |
| `suggestion_value_adjusted_f1` | 연구용 보조 (production 사용 금지) | strict_action_f1 + (msp × pear × weight) |

## controlled beta 기준

- production candidate gate: `strict_action_f1 ≥ 0.90` (Layer 1).
- controlled beta 진입 검토: `manual_suggestion_precision ≥ 0.80` (Layer 2,
  Internal Alpha feedback 후 측정). external beta / release 표현은 사용하지
  않으며, 두 기준 충족 시 별도 판정 PR 영역.

## 분리 원칙 (절대 준수)

1. `strict_action_f1` 산식 변경 금지 — Layer 1 은 기존 계약 그대로.
2. production gate threshold(0.90) 변경 금지.
3. gold=0/pred≥1 은 Layer 1 에서 여전히 FP — FP→TP 임의 처리 금지.
4. gold label / normalized_action label 수정 금지.
5. Layer 2 보조 지표는 production gate 로 사용 금지 (연구/UX 판단 전용).
6. `suggestion_value_adjusted_f1` 은 연구용 — production 의사결정 금지.
