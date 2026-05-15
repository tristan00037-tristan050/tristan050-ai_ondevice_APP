# PR #723 Algorithm Branch D measurement Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- ops_pr: 721
- branch: D
- patch_type: measurement_only
- verdict: MEASURED_ONLY

## deadline_f1 breakdown
- deadline_f1: 0.8092
- tp / fp / fn: 53 / 7 / 18
- actionable_match_rate: 0.978
- mismatch_rows: 54

## type_distribution
- NONE: 391
- HARD: 50
- SOFT: 21
- CONDITION: 16
- INQUIRY: 11
- URGENCY: 11

## 5종 혼동 카테고리
- INQUIRY_misclassified_as_HARD_or_SOFT: count=1, rate=0.0909
- URGENCY_misclassified_as_SOFT: count=0, rate=0.0
- URGENCY_misclassified_as_HARD_or_SOFT: count=0, rate=0.0
- CONDITION_misclassified_as_HARD_or_SOFT: count=0, rate=0.0
- HARD_misclassified_as_SOFT: count=14, rate=0.28
- SOFT_misclassified_as_HARD: count=0, rate=0.0
- NONE_misclassified_as_actionable: count=6, rate=0.0153

## relative time normalization
- relative_time_total: 89
- mismatch_count: 22
- mismatch_rate: 0.2472

## Branch D readiness
- enter_branch_d_assessment_pr: True
- enter_branch_d_main_pr: True
- next_step: Branch D 본진입 PR 권장 (deadline classifier patch)