# Branch D Quantitative Readiness (PR #723 측정 결과 기준)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- ops_pr: 721
- branch: D
- patch_type: measurement_only
- verdict: MEASURED_ONLY

- deadline_f1: 0.8092 (threshold 0.9)
- actionable_match_rate: 0.978
- relative_time_mismatch_rate: 0.2472
- enter_branch_d_assessment_pr: True
- enter_branch_d_main_pr: True
- next_step: Branch D 본진입 PR 권장 (deadline classifier patch)

## 5종 혼동 카테고리 비중
- INQUIRY_misclassified_as_HARD_or_SOFT: count=1, gold_total=11, rate=0.0909
- URGENCY_misclassified_as_SOFT: count=0, gold_total=11, rate=0.0
- URGENCY_misclassified_as_HARD_or_SOFT: count=0, gold_total=11, rate=0.0
- CONDITION_misclassified_as_HARD_or_SOFT: count=0, gold_total=16, rate=0.0
- HARD_misclassified_as_SOFT: count=14, gold_total=50, rate=0.28
- SOFT_misclassified_as_HARD: count=0, gold_total=21, rate=0.0
- NONE_misclassified_as_actionable: count=6, gold_total=391, rate=0.0153