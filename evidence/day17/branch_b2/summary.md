# PR #722 Algorithm Branch B-2 Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- ops_pr: 721
- branch: B-2
- patch_type: over_extraction_guard
- verdict: MEASURED_ONLY

## mixed 116 2차 taxonomy 분포
- MIXED-F_deadline_action_entangled: 13
- MIXED-G_unrecoverable_by_prompt_schema: 31
- MIXED-A_borderline_parser_llm: 67
- MIXED-B_both_partial_correct: 3
- MIXED-D_normalization_semantic_gap: 2

## A/B/C simulation 결과
- A: fp=20, fn=4, f1=0.7647
- B: fp=19, fn=4, f1=0.7723, over_blocked=1
- C: fp=45, fn=4, f1=0.6142, decomp_applied=26
- selected: B_over_guard_only (B action_fp Δ ≤ 0 + safety preserved)
- B vs A: fp Δ -1, f1 Δ 0.0076
- C vs A: fp Δ 25, f1 Δ -0.1505

## AB composition (sentinel #7)
- composition_ok: True / fail_class: AB_COMPOSITION_NATURAL_SHORTAGE
- natural_shortage: True / shortage_log: 1

## Full Eval 500 (12 measurement)
- normalized_action_f1:        0.6182
- action_fp / action_fn:       234 / 13
- multi_action_split_accuracy: 0.8621
- deadline_f1:                 0.8092
- false_deadline_rate:         0.014
- no_action_fp_rate:           0.0273
- auto_apply_precision:        0.0
- g22 / g23:                   0 / 0
- schema_valid_rate:           1.0
- coverage:                    None
- evidence_missing_action_count: 1
- over_extraction_guard_block_count: 29

## gold_review_queue: 4건 (Branch C 분리 — 승격 금지)