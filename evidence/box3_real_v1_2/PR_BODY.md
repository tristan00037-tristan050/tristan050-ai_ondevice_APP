# Box3 real 융합 — 3채널 단일 계약 융합 (maindev·alg·codex)

**STATUS=PARTIAL_REAL_GATED_ASSET_PENDING · 머지 금지(재검토 APPROVE + 대표 승인 전 보류)**

3채널(maindev `bd18ae64` · alg `74884fbe` · codex `658b28f2`) 결과물을 모듈별 최선만
골라 **단일 계약**으로 융합(봉합 금지). 골격 PR #770(`9b39c936`) 머지본 위 적층, 융합
후 단일 PR 1건. 본 브랜치(`feat/box3-real-followup-v1-2`)의 직전 codex-only 추가분을
융합본으로 교체.

## 모듈별 융합 베이스
| 모듈 | 베이스 | 흡수 |
|---|---|---|
| 계약 3객체 | maindev `real_contracts` | codex `from_raw`/`__post_init__`·`to_response_dict`/`to_persistable_dict`·`ClaimSupportLevel` Literal·audit `stage_trace`·`contract_only`/`real_claim_allowed` |
| grounding | maindev `real_grounding` (numeric·부정모순·evidence_kind·overlap 0.60) | alg `_facts`/사실대조 · codex `ClaimGroundingSummary`/citation |
| pipeline | codex `run_box3_real_*` (stage_trace + 골격 manifest 재사용) | maindev `_call_runner_with_timeout` · alg contract_only 분기·table_figure coverage |
| asset_manifest | 골격 PR #770 재사용(신규 0) | — |
| eval / sidecar / self_check | 골격 verdict-only 40건 · maindev route(legacy fallback) · codex self_check | — |

## 단일 계약 스펙(3장 정본)
- `ClaimVerdict`: support_level `supported|unsupported|no_evidence|non_claim`, reason_code `EVIDENCE_ENTAILS|EVIDENCE_CONTRADICTS|NO_MATCHING_EVIDENCE|NON_FACTUAL`.
- `Box3RealRuntimeEnvelope`: sidecar memory only(저장 금지) — `from_raw` DLP 검증.
- `Box3RealVerdict`: `to_response_dict()`(draft 포함) / `to_persistable_dict()`(digest-only) 분리 + `contract_only`/`real_claim_allowed`.
- `Box3RealAuditRecord`: digest-only persist(`assert_audit_record_is_digest_only`) + `stage_trace`.
- pipeline 출력: 7단계 `stage_trace[]` + `contract_only` + `real_claim_allowed`.

## 정직성 경계
- 실제 real claim 닫힘(`actual_pass_box3_real_claim=false`). helper4/7/8 full SHA·인터페이스 인벤토리 PENDING.
- 기본 입력 경로는 항상 `contract_only`(asset PENDING). fixture manifest 는 게이트 검증 전용.

## Evidence (verdict-only)
- 융합 테스트 23 passed · box3 회귀 93 passed(무회귀) · self_check `PARTIAL_REAL_GATED_ASSET_PENDING`
- 봉합 0(단일 계약 1벌) · asset_manifest 신규 0(diff 0줄) · 계약 `schemas/*` 변경 0
- raw/path/secret/PII 누출 0 · 바이너리 artifact 0 · 실제 학습 0 · production claim 0

## 절대 금지 준수
봉합 0 · asset_manifest 신규 0 · 개별 PR 0(단일 1건) · 입력 digest-only 생성 0 · 과대주장 0 · raw 노출 0.

## 머지 정책
**머지 금지.** 단일 PR unresolved 0 + CI green → 재검토 5단 → 대표 머지 전까지 보류.
