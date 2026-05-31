# PR-E: Connect Loop Learning Candidate Gate

**STATUS=PASS_PR_E_LEARNING_CANDIDATE_GATE_CANDIDATE**

## Base 정합
- MAIN_HEAD=`de63a90674edfe7f5fc1c86e61e2fc979b9a8328`
- 테스트 실행 head=`3eddc3e12c4a6e9a0b020b9f7dfff159bc35d07b`
- 구현 정정 head=`3eddc3e12c4a6e9a0b020b9f7dfff159bc35d07b`
- 브랜치=`feat/connect-loop-learning-candidate-gate`
- 계약 정본 `schemas/connect_loop/*`: 수정 0

## 4라운드 정정
- P1 DLP regex: 프로젝트 스코프 포함 hyphenated `sk-` 계열 토큰을 secret으로 탐지하도록 보강(패턴 리터럴은 evidence 마스킹)
- P2 idempotency: `learning_event_created=true` usage_log는 후보 재선정에서 제외
- P2 tenant_scope: 누락 또는 enum 외 값은 event 빌드 전 `TENANT_SCOPE_INVALID`로 fail-closed

## 5라운드 정정
- P2 store idempotency: 동일 `source_usage_log_id`의 두 번째 learning_event append는 `DUPLICATE_SOURCE_USAGE_LOG`로 fail-closed
- P2 persisted scalar DLP: 저장 필드 scalar에서도 email/phone/RRN/card PII를 secret/local path와 동일하게 차단
- JSONL restart idempotency: 기존 JSONL을 hydrate해 retry/backfill 중복 append를 차단

## v2.2 근본 재검토 정정
- `persisted_safety.py` 단일 guard 추가: secret/path/PII/raw-field를 한 곳에서 전수 스캔
- create/approve/reject/expire/store append 전 경로가 `_safe_return_event` 또는 `_enforce_persisted_safety` 통과
- OS 무관 path matrix 포함: macOS/Linux temp/private temp/volume/Windows backslash/Windows slash/UNC/file URL
- 국제/미국식/KR 전화번호 PII matrix 포함
- canonical `+82` 국제 전화번호 PII matrix 포함
- reject/expire/expired approval path의 persisted-scalar DLP 우회 차단

## Scope
- usage_log.v1.1 digest-only에서 학습 후보 식별
- `LearningGateInput.v1` 내부 계약 빌드
- DLP guard는 boolean만 저장하고 매칭 원문은 반환하지 않음
- `learning_event.v1` 생성과 정본 schema self-validate
- CANDIDATE / APPROVED / REJECTED / EXPIRED 상태 전이
- `verified_for_training=true`는 APPROVED + policy approved + DLP pass에서만 허용
- usage_log immutable 유지, `learning_event_link_index`만 별도 생성

## Non-scope
- 실제 모델 학습 0
- LoRA, adapter, GGUF, safetensors 등 모델 artifact 0
- Verified Company Adapter 승격 0
- Company DNA Graph / AI Action Receipt 구현 0
- production / release claim 0

## Evidence
- targeted safety: `39 passed`
- PR-E v2.2 묶음: `89 passed`
- 전체 `tests/connect_loop`: `472 passed`
- `py_compile`: PASS
- `git diff --check`: PASS
- `CONTRACT_MODIFIED_ZERO=true`
- `MODEL_BINARY_ARTIFACT_ZERO=true`
- `TRAINING_SCOPE_CREEP_ZERO=true`
- `RAW_SECRET_FIELD_ZERO=true`
- `ABSOLUTE_PATH_LEAK_ZERO=true`
- `EVIDENCE_LEAK_ZERO=true`

## Disclosure
- usage_log는 학습 데이터가 아니다.
- learning_event는 approved_text_ref/digest + 정책 승인 + DLP pass + 보존기간을 모두 통과한 경우에만 생성된다.
- 실제 회사화 학습과 adapter 승격은 후속 그룹A 범위다.
- 머지는 금지한다. Codex 재검토 unresolved=0과 CI green 확인 전까지 보류한다.
