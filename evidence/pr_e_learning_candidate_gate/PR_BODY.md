# PR-E: Connect Loop Learning Candidate Gate

**STATUS=PASS_PR_E_LEARNING_CANDIDATE_GATE_CANDIDATE**

- MAIN_HEAD=`de63a90674edfe7f5fc1c86e61e2fc979b9a8328` (PR #768 머지본, 지시서 전제 일치)
- 작업 트리: `connect-loop-usage-accumulator` @ `feat/connect-loop-learning-candidate-gate`
- 계약 정본: `schemas/connect_loop/learning_event_v1.schema.json`, `usage_log_v1_1.schema.json` (main 머지본, **수정 0**)

## Scope (포함)
- usage_log.v1.1 digest-only → 학습 후보 식별 (`learning_candidate=true` + `policy_decision=allow` + `integration_mode=real` + `real_validation_done=true` + raw/external 불변식)
- `LearningGateInput.v1` 내부 계약 빌드 (PR-A schema 수정 아님)
- DLP guard: PII/secret/policy_violation 을 **boolean만** 저장 (원문/토큰/경로 미반환·미저장)
- `learning_event.v1` 생성 + 정본 schema self-validate
- 상태기계: CANDIDATE / APPROVED / REJECTED / EXPIRED 전이 함수 + 불변식
- `verified_for_training`: 승인 전 false, `status=APPROVED + policy approved + DLP pass` 일 때만 true (스키마 if/then 이중 강제)
- raw leak guard: raw 필드명·파일명·로컬경로·token·secret 0
- usage_log 불변 + `learning_event_link_index` (source_usage_log_id ↔ learning_event_id)

## Non-scope (제외 — 그룹A / 후속)
- 실제 모델 학습 0 / LoRA·adapter 0 / GGUF·safetensors 등 모델 artifact 0
- Verified Company Adapter 승격 0 / Company DNA Graph 0 / AI Action Receipt 0
- PR-A/B/C/D 계약·schema 파일 수정 0 (BLOCK)

## Evidence (실측)
- `heads.txt` — MAIN_HEAD / PR_HEAD / BRANCH
- `pytest_connect_loop_pr_e.txt` — **397 passed** (전체 connect_loop 무회귀)
- `pytest_pr_e_verbose.txt` — PR-E 신규 **14 passed** (지시서 §10 테스트 1~12 커버)
- `guard_scans.txt`:
  - `CONTRACT_MODIFIED_ZERO=true`
  - `MODEL_BINARY_ARTIFACT_ZERO=true`
  - `TRAINING_SCOPE_CREEP_ZERO=true`
  - `RAW_SECRET_FIELD_ZERO=true`

## Disclosure
- usage_log 는 학습 데이터가 아니다 (digest-only, immutable).
- learning_event 는 approved_text_ref/digest + 정책 승인 + DLP pass + 보존기간을 모두 통과한 경우에만 생성된다.
- `verified_for_training=true` 는 `APPROVED + policy approved + DLP pass` 일 때만 성립한다.
- 실제 회사화 학습·adapter 승격·배포는 그룹A Verified Company Adapter 범위 (본 PR 아님).
