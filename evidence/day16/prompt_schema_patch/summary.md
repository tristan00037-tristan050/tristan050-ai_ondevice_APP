# PR #720 Algorithm Branch B prompt/schema patch Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 718
- branch: B
- patch_type: prompt_schema
- verdict: MEASURED_ONLY
- alignment_cycle: 1차 측정

## Multi-action collapse evidence
- total_collapse: 4
- decomp_recoverable: 3 (75.0%)

## Parser vs LLM both_fail 4축 분해
- both_fail_total: 120
- parser_limit / llm_limit / schema_limit / gold_limit: 0 / 0 / 0 / 4

## AB Eval 50
- composition_ok: False / fail_class: AB_COMPOSITION_MISMATCH
- A f1: 0.7959
- B f1: 0.7525
- delta f1: -0.0434
- delta action_fp: 4
- delta action_fn: 1

## Full Eval Impact (12 fields)
- normalized_action_f1:        0.5976
- action_fp / action_fn:       261 / 11
- multi_action_split_accuracy: 0.8621
- deadline_f1:                 0.8092
- false_deadline_rate:         0.014
- no_action_fp_rate:           0.0273
- auto_apply_precision:        0.0
- g22_strict_warning_count:    0
- g23_hard_violation_count:    0
- schema_valid_rate:           1.0
- coverage (sentinel #6):      {'coverage_checked': True, 'expected_samples': 500, 'measured_samples': 500, 'missing_count': 0, 'extra_count': 0, 'duplicate_count': 0, 'fail_class': None}

## Branch C/D/E readiness
- Branch C: enter=False
- Branch D: enter=True
- Branch E: enter=True
- Branch F: ABSOLUTELY_FORBIDDEN (자문 13.5)