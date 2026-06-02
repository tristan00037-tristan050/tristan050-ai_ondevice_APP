# Box3 real 융합 v1.0 Result Summary

STATUS=PARTIAL_REAL_GATED_ASSET_PENDING

## 융합(3채널 → 단일 계약, 봉합 금지)

3채널(maindev `bd18ae64` · alg `74884fbe` · codex `658b28f2`) 결과물을 모듈별 최선만
골라 **단일 계약**으로 융합. 골격 PR #770(`9b39c936`) 위 적층.

- 계약 3객체: 베이스 maindev `real_contracts` + 흡수 codex 경계메서드
  (`from_raw`/`__post_init__`, `to_response_dict`/`to_persistable_dict`,
  `ClaimSupportLevel` Literal, audit `stage_trace`, `contract_only`/`real_claim_allowed`).
- grounding: 베이스 maindev `real_grounding`(numeric·부정모순·evidence_kind·overlap 0.60)
  + 흡수 alg `_facts`/사실대조 + codex `ClaimGroundingSummary`/citation. 4판정
  (supported/unsupported/no_evidence/non_claim) · reason_code 4종 정본 고정.
- pipeline: 베이스 codex `run_box3_real_*`(stage_trace + 골격 manifest 재사용) + 흡수
  maindev `_call_runner_with_timeout` + alg contract_only 분기·table_figure coverage.
  7단계 고정.
- asset_manifest: 골격 PR #770 재사용(신규 구현 0 — `manifest_allows_real`/
  `manifest_block_reason`). eval: 골격 verdict-only 40건(alg) 재사용. sidecar: maindev
  route(legacy fallback 보존). self_check: codex(repo-root sys.path 가드).

## 정직성 경계

- 실제 real claim 은 닫혀 있다(`actual_pass_box3_real_claim=false`).
- helper4/helper7/helper8 full SHA·인터페이스 인벤토리는 본 repo 상태에서 PENDING.
- 기본 입력 경로는 항상 `contract_only`(asset PENDING) — fixture manifest 는 게이트
  동작 검증 전용이며 실제 자산 인벤토리 pass 가 아니다.

## 검증 (verdict-only)

- 융합 테스트(`tests/cards/box3/test_box3_real_*_v1_2.py`): 23 passed
- box3 회귀 세트(`tests/cards/box3` + `tests/connect_loop` box3): 93 passed (무회귀)
- self_check: `PARTIAL_REAL_GATED_ASSET_PENDING`, real_path_fixture_pass=true
- 봉합 0: ClaimVerdict/Envelope/Verdict/AuditRecord 정의 각 1곳(`real_contracts.py`)
- asset_manifest 신규 0 (vs `9b39c936` diff 0줄), 계약 정본 `schemas/*` 변경 0
- `external_send_zero=true`, `raw_persistence_zero=true`, raw/path/secret/PII 누출 0
- 신규 바이너리 artifact 0, 실제 학습 0, production/release claim 0

## Evidence Files

- `asset_inventory_status_v1_2.json`
- `pipeline_smoke_v1_2.json`
- `metric_summary_v1_2.json`
- `pytest_box3_real_v1_2.txt`
- `package_manifest_v1_2.json`
