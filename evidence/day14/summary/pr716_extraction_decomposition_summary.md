# PR #716 Extraction Error Decomposition Summary

## STATUS=MEASURED_ONLY

## 1. Input
- PR #715 merge SHA: 194d07eec4a196df65f9801f5ad35ed67c60520b
- dataset_id: card1_evalset_v1_1_500
- total_samples: 500

## 2. 6 산출물 핵심 (top 3)
### Action FP
- FP-E_report_question_as_action: 113
- FP-C_wrong_normalized_action: 101
- FP-A_hallucinated_action: 24
### Action FN
- FN-B_missed_sub_action_in_multi: 4
- FN-A_missed_single_action: 4
- FN-D_evidence_present_but_not_extracted: 4
### Deadline: FP 7 / FN 4 / mismatch 14
### Parser vs LLM: record-level disagreement 214
### Mapping gaps: OOV 77 unique
### Prompt/schema candidates: 10 (적용 금지)

## 3. 메인 추가 evidence 4종
- fp_auto_apply: 0
- fn_auto_apply: 27
- no_action_fp: 21
- verifier_interaction: 29

## 4. root_cause_matrix 상위 5
- mapping_gap: count=132 top_cause=vocabulary
- FP-E_report_question_as_action: count=113 top_cause=prompt
- FP-C_wrong_normalized_action: count=101 top_cause=vocabulary
- FP-A_hallucinated_action: count=24 top_cause=prompt
- FP-D_no_action_violation: count=21 top_cause=prompt

## 5. PR #717 분기 추천
- primary cause: prompt
- branch: PR #717C — prompt patch first

## 6. 결론
- safe_to_patch_prompt: true
- safe_to_patch_schema: true (별도 PR #717D 영역)
- requires_model_training: false (현 단계 prompt/schema/vocabulary 우선)

## 7. verdict 권고
MEASURED_ONLY (PR #716 범위, 공식 판정은 PR #718 단계에서 진행)