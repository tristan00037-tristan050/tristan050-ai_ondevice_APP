# Extraction Error Decomposition Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 715
- merge_sha: 194d07eec4a196df65f9801f5ad35ed67c60520b
- verdict: MEASURED_ONLY
- total_samples: 500
- head_sha_aligned: 0072c81a63733101d9bb8151c45fc133698301ce
- alignment_cycle: 1차 정정 후

## Action FP — total 259
- FP-E_report_question_as_action: 113 (22.6%)
- FP-C_wrong_normalized_action: 101 (20.2%)
- FP-A_hallucinated_action: 24 (4.8%)
- FP-D_no_action_violation: 21 (4.2%)

## Action FN — total 12
- multi_action_total 29 / full_miss 0 / partial 0 / collapse 4
- FN-B_missed_sub_action_in_multi: 4
- FN-A_missed_single_action: 4
- FN-D_evidence_present_but_not_extracted: 4

## Deadline
- deadline_FP: 7
- deadline_FN: 4
- deadline_type_mismatch: 14
- INQUIRY → HARD/SOFT: 1
- URGENCY → deadline: 0
- CONDITION → deadline: 0

## Parser vs LLM disagreement
- record-level: 214
- llm_wins (intent gold==pred): 346
- both_fail: 154

## Mapping gaps
- canonical 'other' bucket: 132
- OOV unique action_texts: 77

## Additional evidence counts
- fp_auto_apply_cases:     294
- fn_auto_apply_cases:     1
- no_action_fp_cases:      21
- verifier_interaction:    29