# A 어댑터 실작동 producer probe — alg10 v1.2

STATUS=PROBE_RECORDED_DIGEST_ONLY
Base 기준: `main 6751a3e5` (지시서 기준)

## 확인된 골격

- `LearningIntakeRunner.ingest(candidate)`는 `gate.evaluate(candidate)`가 accepted일 때만 `ArtifactQueue.append_candidate()`를 호출하고, `accepted/drop_reason/queue_appended/record_digest` 요약을 반환한다.
- `UnifiedLearningIntakeGate.evaluate()`는 `validate_candidate_contract()` 이후 policy/raw/external/auto_apply/model_training/peft_training/integration_mode 불변식을 재확인한 뒤 registry adapter로 넘긴다.
- `integrated_learning_candidate.v1` 계약은 `candidate_id=ilc-*`, `target_kind`, `learning_source_type`, `payload_digest`, `expected_effect_digest`, `verification`, `source_refs`를 요구하고, `integration_mode`를 전역 금지 필드로 둔다.
- `BoxRulePatchAdapter.verify()`는 `rule_target`, `group_a_fixed_eval_passed`, `runtime_hotpatch`, `changed_files`, `tests_to_run`, `expected_current_digest`, `proposed_diff_digest`를 검증한다.
- A 어댑터 allowlist의 토큰 파일명은 `butler_pc_core/accounting/rulebase_learning/rule_tokens.json`이다. `rule_token_config.json`은 반례로 `DIFF_FILE_NOT_ALLOWED`가 되어야 한다.

## 이 패치가 지키는 범위

- `butler_pc_core/learning_core/*` 변경 0.
- Box5 runtime 분류 로직 변경 0.
- candidate/queue/log에는 원문, 계좌, 파일명, full diff, local path, vault/keyring ref 저장 0.
- producer는 `verified_rule_base_candidate.v1` 또는 Box5 artifact를 `integrated_learning_candidate.v1`로 재포장한다.
- 기존 `vrb-*` 후보 ID를 재사용하지 않고 안정 digest 기반 `ilc-*` ID를 새로 만든다.

## 기대 수용 게이트 연결

- A1: `ingest_verified_box5_rule_patch()` → `runner.ingest()` → queue append.
- A2: envelope/payload가 `contracts.py`와 `box_rule_patch.py`를 모두 통과.
- A3: `group_a_fixed_eval_passed=False`는 `GROUP_A_FIXED_EVAL_NOT_PASSED`.
- A4: raw/vault/path 계열 문자열은 producer 단계 또는 contract 단계에서 fail-closed.
- A5: `runtime_hotpatch=True`는 `RUNTIME_HOTPATCH_FORBIDDEN`; candidate는 `auto_apply_to_runtime=False`.
- A6: learning_core diff 0.
- A10: `rule_token_config.json` 반례는 `DIFF_FILE_NOT_ALLOWED`.

## 정직성

이 probe는 원문·계좌·fixture 내용을 포함하지 않는다. 실제 대표님 repo에서 `git apply --check`, 전체 pytest, Group A L9b 49 고정셋은 아직 수행하지 않았으며, 본 ZIP의 evidence는 mock validation only이다.
