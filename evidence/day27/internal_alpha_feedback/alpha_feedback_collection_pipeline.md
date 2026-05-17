# Alpha Feedback Collection Pipeline

## metadata
- source_pr: 733
- branch: Internal-Alpha-Feedback
- verdict: MEASURED_ONLY

## 파이프라인 단계

```
manual_suggestion 표시 → user category 선택 → collector
  → digest computation → privacy guard → audit logger → internal storage
```

## collector module

manual_suggestion 표시 후 user 의 4 카테고리(accept/dismiss/irrelevant/
unsafe) 선택을 수신한다. `feedback_id` 를 발급하고 schema v1 레코드를
구성한다.

## digest computation

raw suggestion context text → `sha256` digest (`_digest()`). raw text 는
저장하지 않으며 `suggestion_context_digest` 필드에 digest 만 기록한다.
`timestamp_digest` 도 deterministic hash — wall-clock 미의존 (강화 안건 10).

## privacy guard

collector 출력 레코드에 raw user text 가 포함되지 않음을 검증한다. 본 PR
측정 결과 raw_text_leak = 0건 (`alpha_feedback_privacy_audit.md`).

## audit logger

모든 feedback 레코드에 `audit_log_id` 를 부여하고 감사 로그에 기록한다.
feedback 레코드 수 == audit log 엔트리 수 (1:1 정합).

## storage

internal only — 외부 전송 경로 없음. encrypted at rest (배포 환경 정책).
feedback 데이터는 측정 집계에만 사용하며 production decision 에 직접
반영하지 않는다.

## measurement

수집된 user_category 집계 → `manual_suggestion_precision = accept /
(accept + dismiss + irrelevant + unsafe)`. option B (synthetic) 는 알려진
synthetic 입력을 파이프라인에 통과시켜 집계 산식 정합을 검증한다.
