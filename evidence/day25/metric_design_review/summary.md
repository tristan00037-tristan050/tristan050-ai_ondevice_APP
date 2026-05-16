# PR #731 — Metric Design Review Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 731
- branch: Metric-Design-Review
- patch_type: metric_contract_redesign_analysis_only
- verdict: MEASURED_ONLY

## 본 PR 의 본질 (정직 보고)
- 분석/설계 PR — 평가 계약(metric contract) 2 Layer 분리 설계.
- gold / normalized_action label / 알고리즘 / threshold 변경 0건.
- strict_action_f1 산식 불변 (= normalized_action_f1 0.6182).
- FP→TP 임의 처리 없음 (gold=0/pred>=1 은 Layer 1 에서 여전히 FP).

## Layer 2 분류 (MIXED-A 67건)
- A3 product_equivalent: 32
- A4 true_over_extraction: 29
- A5 metric_contract_gap: 6
- A6 unresolved_user_value: 0 (Internal Alpha feedback reserved)

## 보조 지표
- product_equivalent_action_rate: 67건 0.4776 / 30건 sample 0.5667
- dangerous_over_extraction_rate: 67건 0.4328 / 30건 sample 0.2333
- strict_action_f1: 0.6182 (production gate 0.9)
- manual_suggestion_precision: 측정 미가능 (Internal Alpha feedback 필요)
- suggestion_value_adjusted_f1: 측정 미가능 (연구용 — production 금지)

## expected vs observed (Standard 12 — 정직 보고)
- expected (자문 5차): Layer 분리 후 manual_suggestion_precision >= 0.8 가능성
- observed: 측정 미가능 — Internal Alpha feedback 필요 (PR #733 Final Beta Readiness 후 측정)
- confidence: low (자문 5차 정합, 자문 정량 추정 한계 인지)

### PR #730 A3 재조정 (분류 정밀화 — 측정값 임의 조정 아님)
- 자문 인계는 30건 sample A3=23 (product_equivalent_rate 0.767) 으로 추정.
- 2-Layer contract 재분류: 30건 sample A3=17 / A5=6. PR #730 A3(23) = A3 product_equivalent(17) + A5 metric_contract_gap(6, gold>=1).
- PR #730 4-subtype 의 A3 가 gold>=1 동일라벨 케이스를 포함했던 것을, 2-Layer contract 가 A5 로 분리 — Metric Design Review 의 정상 산출물 (FP→TP 처리 아님, gold 미수정).
- 30건 sample rate 0.5667 vs 67건 전체 0.4776 — 67건 전체를 권위 측정값으로 본다.

## metric contract version
- v1.0.0 (strict only) → v2.0.0 (strict + suggestion 2 Layer) — SemVer MAJOR bump (Standard 10)
- before/after delta 0 (strict layer 불변) / policy drift_rate 0

## main 측정값 정합 (변동 0건)
- strict_action_f1 0.6182 / deadline_f1 0.8702 / action_fp 234 — 불변

## verdict: MEASURED_ONLY
분석/설계 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.