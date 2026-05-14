# Prompt / Schema Patch Candidates (PR #716, 적용 금지)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 715
- merge_sha: 194d07eec4a196df65f9801f5ad35ed67c60520b
- verdict: MEASURED_ONLY

## A/B small eval 설계 (50건)
- action FP/FN high-risk 20
- deadline 오류 15
- parser_vs_llm disagreement 10
- mapping gap 5

## 비교 지표
- normalized_action_f1 / deadline_f1 / false_deadline_rate
- no_action_fp_rate / schema_valid_rate / G23 hard violation

## 사전 평가 항목 (calibration 안정성)
- raw_intent_confidence 분포 변화
- raw_action_confidence 분포 변화
- pred action count 분포 변화
- schema_valid_rate 변화
- auto_apply candidate count 변화

## patch_candidates_top_10 (10개 초과 금지)
1. prompt: REPORT/QUESTION 어미 인식 강화 (FP-E)
2. prompt: NO_ACTION 부정형 명시 (FP-D)
3. prompt: 행동동사 동반 시에만 action 생성 규칙 (FP-A)
4. schema: actions minItems=1 when intent ∈ {REQUEST, COMMAND}
5. schema: evidence required + must_be_substring_of_source
6. prompt: multi-action 시 분리 지시 (FN-B/C)
7. vocabulary: 빈출 OOV action 매핑 후보 (mapping gaps 참조)
8. prompt: deadline INQUIRY/URGENCY/CONDITION 구분 명시 (deadline FP)
9. prompt: deadline 미존재 시 deadline=null 강제
10. parser hint: 행동동사 list 확장 (parser_vs_llm 분석 후)

## PR #716 최종 결론
- safe_to_patch_prompt: true (위 1~3,6,8,9 후보 안전)
- safe_to_patch_schema: true (위 4,5 후보 안전, 별도 PR 영역)
- requires_model_training: false (현 단계 prompt/schema/vocabulary 우선)