# PR #733 — Internal Alpha Feedback Instrumentation Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 733
- branch: Internal-Alpha-Feedback
- patch_type: feedback_instrumentation_no_algorithm_change
- verdict: MEASURED_ONLY

## 본 PR 의 본질
- 계측/인프라 PR — alpha feedback schema + collection pipeline +
  privacy audit + manual_suggestion_precision 측정 정착.
- 알고리즘 patch 0 / prompt·model weight 변경 0.
- raw user data 저장 0 (digest 만) / 외부 전송 0 / auto_apply OFF.

## manual_suggestion_precision 측정 (option A — simulation proxy)
- manual_suggestion 대상 (A3): 32건
- reviewer_strict: {'irrelevant': 11, 'accept': 15, 'dismiss': 6} → msp 0.4688
- reviewer_lenient: {'irrelevant': 11, 'accept': 21} → msp 0.6562
- Cohen's κ (strict vs lenient): 0.6735 (< 0.7 — 기준 재정의 필요)

## expected vs observed (Standard 12 — 정직 보고)
- expected (자문 5차 8.2): manual_suggestion_precision >= 0.8
- observed (primary, reviewer_strict): 0.4688
- delta: -0.3312 (미충족)
- confidence: low — msp 는 deterministic simulation proxy. 실제 Internal Alpha user feedback (option C)는 본 PR 범위 밖이며, 권위 측정은 정식 Internal Alpha 배포 후 가능.

## Controlled Beta readiness
- 기준 충족: 5/7
- Controlled Beta ready: False
- 미충족 기준: ['strict_action_f1 >= 0.90 (production gate)', 'manual_suggestion_precision >= 0.80']

## main 측정값 정합 (변동 0)
- deadline_f1 0.8702 / strict_action_f1 0.6452 / action_fp 207 / safety 6종 — 전부 불변. metric contract v2.0.0 유지.

## privacy audit
- feedback 레코드 raw text leak: 0건 (목표 0)
- 모든 레코드 digest 저장 / 외부 전송 0 / audit_log_id 정합.

## verdict: MEASURED_ONLY
계측 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.