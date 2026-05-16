# PR #730 — Branch C-lite Gold/Action Unit Review Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 730
- branch: C-lite
- patch_type: gold_action_unit_review_analysis_only
- verdict: MEASURED_ONLY

## 본 PR 의 본질 (정직 보고)
- 분석 PR — gold / normalized_action label / 알고리즘 변경 0건.
- main 측정값 (normalized_action_f1 0.6182 / deadline_f1 0.8702 / action_fp 234) 불변.

## MIXED-A 30건 review 결과
- A3_product_equivalent_prediction: 23건
- A4_true_model_error: 7건
- action_unit_mismatch (A1): 0건 / 30

## expected vs observed (Standard 12)
- expected (자문 추정 — Branch C 진입 기준선): A1 >= 8/30
- observed (실측): A1 = 0/30
- delta: -8
- 정직 보고: 예상 미달 — 정량 반전
  MIXED-A 67건 중 61건이 gold=0/pred>=1 (over-extraction) — 자문이 추정한 action unit granularity mismatch 가 아니라 A3/A4 영역이 주류.

## Branch C 진입 판정
- MIXED-A 본질이 A3/A4 영역 — 정식 Branch C 진입 기준 미달. metric design review 우선 권고

## verdict: MEASURED_ONLY
분석 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.