# PR-E: Connect Loop Learning Candidate Gate

**STATUS=PASS_PR_E_LEARNING_CANDIDATE_GATE_CANDIDATE**

## Base 정합
- MAIN_HEAD=`de63a90674edfe7f5fc1c86e61e2fc979b9a8328`
- 최신 검증 코드/evidence head=`503b4c960d514eae8300ce80b23d7be955997041`
- 브랜치=`feat/connect-loop-learning-candidate-gate`
- 계약 정본 `schemas/connect_loop/*`: 수정 0

## 4라운드 정정
- P1 DLP regex: `sk-proj-...` 포함 hyphenated `sk` 토큰을 secret으로 탐지하도록 보강
- P2 idempotency: `learning_event_created=true` usage_log는 후보 재선정에서 제외
- P2 tenant_scope: 누락 또는 enum 외 값은 event 빌드 전 `TENANT_SCOPE_INVALID`로 fail-closed

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
- PR-E 묶음: `50 passed`
- 전체 `tests/connect_loop`: `433 passed`
- `py_compile`: PASS
- `git diff --check`: PASS
- `CONTRACT_MODIFIED_ZERO=true`
- `MODEL_BINARY_ARTIFACT_ZERO=true`
- `TRAINING_SCOPE_CREEP_ZERO=true`
- `RAW_SECRET_FIELD_ZERO=true`
- `ABSOLUTE_PATH_LEAK_ZERO=true`

## Disclosure
- usage_log는 학습 데이터가 아니다.
- learning_event는 approved_text_ref/digest + 정책 승인 + DLP pass + 보존기간을 모두 통과한 경우에만 생성된다.
- 실제 회사화 학습과 adapter 승격은 후속 그룹A 범위다.
- 머지는 금지한다. Codex 재검토 unresolved=0과 CI green 확인 전까지 보류한다.
