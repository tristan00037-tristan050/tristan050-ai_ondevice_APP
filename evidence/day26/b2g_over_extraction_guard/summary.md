# PR #732 — Branch B-2G Over-extraction Guard Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 732
- branch: B-2G
- patch_type: post_processing_over_extraction_guard
- verdict: MEASURED_ONLY

## 본 PR 의 본질
- post-processing over-extraction guard — prompt / model weight 변경 0.
- gold / normalized_action label / strict_action_f1 산식 변경 0.
- FP→TP 처리 0 (guard 는 over-extracted FP action 제거만).

## Guard 영향 (MIXED-A 67)
- A4 차단: 20/29 (0.6897)
- A3 보존: 32/32 (과차단 0건)
- A5 영향: 0/6

## control vs treatment
- action_fp: 234 → 207 (Δ -27)
- strict_action_f1: 0.6182 → 0.6452
- dangerous_over_extraction_rate: 0.4328 → 0.1915

## expected vs observed (Standard 12 — 정직 보고)
- expected (자문 5차 5.5): A4 >= 24 차단 / action_fp <= 210 / dangerous_over_extraction_rate <= 0.05
  - A4 차단 >= 24: 미충족
  - action_fp <= 210: 충족
  - dangerous_over_extraction_rate <= 0.05: 미충족
  - A3 과차단 0건: 충족
  - A5 영향 0건: 충족
  - strict_action_f1 >= 0.6182: 충족

### 미충족 항목 정직 보고
- A4 차단 20/29: 잔여 9건은 '부탁드립니다' 형(실제 요청과 표면 동일) + '보고드리려고 합니다' 형(A5 card1_100078과 표면 동일). text-only guard 로 안전 차단 시 실제 요청 / A5 gold action 손실 위험 — 차단하지 않는 것이 정합.
- 잔여 A4 는 gold/metric contract review 영역 (B-2G 범위 밖).

## main 측정값 정합
- strict_action_f1 0.6452 (>= 0.6182 유지)
- deadline_f1 0.8702 / safety 6종 — guard 미접촉, 변동 0
- metric contract v2.0.0 유지 (Guard 는 bump 사유 아님)

## verdict: MEASURED_ONLY
post-processing guard PR — 금지 verdict 미사용. forbidden grep 0건.