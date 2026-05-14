# metrics_13 Contract (Day 12 PR #714 영역)

## 정합 영역

| 항목 | 영역 |
|---|---|
| dataset_id | card1_evalset_v1_1_500 (고정) |
| dataset_file | tests/fixtures/card1_evalset_v1_1_500.jsonl (고정) |
| verdict (PR #713) | MEASURED_ONLY |
| verdict (PR #714) | PATCH |
| decision mode | D mode only |

## 정식 판정 필드

- auto_apply_precision
- auto_apply_recall

## 참조 영역 (official decision 미사용)

- auto_apply_rate: reference_only

## 절대 금지 필드

- 정확도 단독 필드 (auto-apply accuracy 류) 금지
- 구버전 gold-v1 dataset 식별자 금지

## Tier 1~4 13지표 (정합 영역)

### Tier 1 Hard Safety (5)
1. verifier_error_auto_apply_count
2. false_deadline_rate
3. no_action_fp_rate
4. g22_strict_warning_count
5. g23_hard_violation_count

### Tier 2 Auto-apply (2)
6. auto_apply_precision
7. auto_apply_recall

### Tier 3 Extraction Quality (4)
8. schema_valid_rate
9. normalized_action_f1
10. multi_action_split_accuracy
11. deadline_f1

### Tier 4 Calibration (2)
12. action_ece_after
13. intent_ece_after

## production_candidate_thresholds (Day 11 알고리즘 팀 정합)

| 지표 | 영역 |
|---|---|
| verifier_error_auto_apply_count_max | 0 |
| false_deadline_rate_max | 0.02 |
| no_action_fp_rate_max | 0.03 |
| g22_strict_warning_count_max | 0 |
| g23_hard_violation_count_max | 0 |
| auto_apply_precision_min | 0.95 |
| auto_apply_recall_min | 0.70 |
| schema_valid_rate_min | 0.98 |
| normalized_action_f1_min | 0.90 |
| multi_action_split_accuracy_min | 0.85 |
| deadline_f1_min | 0.90 |
| action_ece_after_max | 0.15 |
| intent_ece_after_max | 0.20 |

## contract 검증 스크립트

`scripts/eval/check_metrics_13_contract.py` (PR #713 P1 정정 시 추가).
