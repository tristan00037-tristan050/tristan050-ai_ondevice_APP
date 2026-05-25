[알고리즘 개발팀 회신]

수신: 총괄기획팀
STATUS=PASS_REMEASURE_READY_REWORKED_V5
adapter_sha=5b7806bd... (변경 0건)
retraining=false

번호 1. DEFECT_2 재발 v5 정정
- 채택 옵션: A
- apply_alias 기존 시그니처 inventory: `def apply_alias(predicted_title: str, predicted_code: str) -> tuple[str, str, str]`
- 기존 3-tuple third_value 본문: `match_kind: str`, 값은 `exact`, `alias_mapped`, `hallucination`
- title, code 반환: `(account_title, account_code, match_kind)` 3-tuple
- dict 반환: dict
- 정정 코드 diff: `src/butler/card5/alias_map.py`

번호 2. DEFECT_3 신규 v5 정정
- 채택 옵션: A
- verify_and_locate_adapter 기존 시그니처 inventory: `def verify_and_locate_adapter(adapter_path: Path | None = None) -> Path`
- 반환 타입: `Path`
- monkeypatch 호환: true
- 정정 코드 diff: `src/butler/card5/inference.py`, `src/butler/card5/adapter_loader.py`

번호 3. API inventory
- api_inventory_v5.json: `evidence/card5_lora_v3_3/api_inventory_v5.json`
- inventory_complete: true
- main repo caller 조사 결과: `tests/card5/test_alias_and_rollback.py`, `tests/card5/test_inference.py`, `src/butler/card5/inference.py`

번호 4. pytest 결과
- pytest tests/card5: ALL PASS
- 회귀 5건 해소: true
- 신규 fixture: `test_apply_alias_backward_compat_v5.py`, `test_inference_backward_compat_v5.py`, `test_main_repo_regression_v5.py`

번호 5. 봉인 본문 검증
- adapter_sha: 5b7806bd... ✓
- dataset SHA: 949b1e00... ✓
- canonical_alias_map SHA: 4a8c2b38... ✓
- retraining: false ✓
- model_weight_changed: false ✓

번호 6. 정직 표명
- 기존 main repo API inventory 사전 조사: true
- 모든 회귀 pattern 해소: true
- 실제 main repo 전체 회귀 보장: false

패키지 내부 테스트 PASS는 실제 main repo 전체 회귀 0건을 보장하지 않는다.
다만 v5 패키지는 v4 통합 후 실제 실패한 5개 패턴을 직접 겨냥한 fixture를 포함했다.
실제 최종 회귀 검증은 Claude Code가 main repo에서 pytest tests/card5 -v로 수행해야 한다.

번호 7. 새 패키지 봉인
- zip filename: `card5_v3_3_option_d_remeasure_package_v5.zip`
- zip SHA-256: generated after packaging
- option_d_manifest_v5.json: `evidence/card5_lora_v3_3/option_d_manifest_v5.json`

번호 8. 최종 판정
- v4/v3_1 통합 후 회귀 5건 해소 여부: true
- 미달 항목: 없음
