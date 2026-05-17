# Alpha Feedback Instrumentation Spec (자문 5차 6)

## metadata
- source_pr: 733
- branch: Internal-Alpha-Feedback
- verdict: MEASURED_ONLY

## 목적

manual_suggestion 에 대한 Internal Alpha user feedback 을 계측하는 인프라를
정착한다. 계측/인프라 PR — 알고리즘 patch 0, prompt/model weight 변경 0.
수집된 feedback 은 production decision 에 직접 반영하지 않으며
(수집/측정만), Controlled Beta 진입 정량 결정의 기반 데이터다.

## Phase 1 — Schema 강화 (PR #731 base)

`alpha_feedback_schema_v1.json` — 7 필드:
- `feedback_id` — feedback 레코드 식별자
- `timestamp_digest` — deterministic hash (강화 안건 10 — wall-clock 비의존)
- `suggestion_id` — suggestion(action) link
- `user_category` — 4 카테고리 enum (accept / dismiss / irrelevant / unsafe)
- `suggestion_context_digest` — redacted digest (raw text 저장 금지)
- `decision_envelope_link` — gold/predicted link
- `audit_log_id` — 감사 로그 link

## Phase 2 — Collection Pipeline

`alpha_feedback_collection_pipeline.md` 참조. collector → digest computation
→ privacy guard → audit logger → internal storage.

## Phase 3 — Measurement Infrastructure

`manual_suggestion_precision = accept / (accept + dismiss + irrelevant +
unsafe)` (자문 5차 6.4). 측정: deterministic reviewer-simulation (option A
proxy) + synthetic pipeline 검증 (option B). 실제 Internal Alpha user
feedback (option C)는 본 PR 범위 밖.

reviewer 일관성: Cohen's κ 측정 (PR #731 labeling guide 정합).

## Phase 4 — Privacy Audit

`alpha_feedback_privacy_audit.md` 참조. raw text 저장 0건 / 외부 전송 0건
/ audit log 정합 정량 보증 (자문 5차 6.3).

## 금지선

- raw user data 저장 금지 (digest 만).
- 외부 전송 금지 (Internal Alpha 폐쇄 환경).
- auto_apply ON 금지 (manual review only).
- feedback 을 production decision 에 직접 반영 금지 (수집/측정만).
