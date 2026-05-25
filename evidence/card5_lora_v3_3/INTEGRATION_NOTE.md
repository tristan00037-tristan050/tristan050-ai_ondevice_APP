# Card 5 v3.3 Option D — V5 Integrated Package

## Source
- Codex v5 zip SHA: 534adccb6d7077089469c21aac8e88792106eae4a46ceeb0cf2932ea36792e40 (base)
- 알고리즘팀 v5 zip SHA: e40e3b75adfe3426cc360436436fedc877c65cae835c5d8894b7542366dfc7d5 (evidence supplement)

## Integration Decision (총괄기획팀)

### Codex v5 채택 사유
1. 보완팀 박스 의무 5건 모두 완전 정합 (api_inventory_v5.json, manifest_v5.json, 신규 fixture, scope_seal_v5, ALGORITHM_TEAM_REPLY_V5.md)
2. ALIAS_MAP_12 본문이 main repo 원본 정합 (12 항목, alias_semantics_changed=false 의무 위반 0건)
3. GitHub repo 직접 read inventory_basis 우월 (git show origin/main)
4. 모듈 분리 (adapter_loader, invariants, rollback, system_prompt, allowlist) — other_required_module_attributes 모두 처리

### 알고리즘팀 v5 보강 본문 (evidence만 추가)
- evidence/accounting27/rework_v5_verification.{json,txt}
- evidence/accounting27/rework_v4_verification.{json,txt}
- evidence/accounting27/rework_v2_verification.{json,txt}
- evidence/accounting27/rework_v2_summary.json
- evidence/card5_lora_v3_3/original_v3_3_metrics.json

## 두 본문 비교 정직 표명

| 본문 | Codex | 알고리즘팀 |
|---|---|---|
| API inventory | 동일 | 동일 |
| apply_alias 3-tuple 복원 | ✅ | ✅ |
| verify_and_locate_adapter 복원 | ✅ (import) | ✅ (직접 정의 + try/except fallback) |
| ALIAS_MAP_12 항목 수 | 12 (원본 정합) | 15 (v4 추가 본문 포함) |
| monkeypatchable 안전성 | ⚠️ import 본문 | ✅ 모듈 내부 직접 정의 |
| str() 입력 캐스팅 | ⚠️ 부재 | ✅ 포함 |

## Phase 4 Pytest 실측 의무
- Claude Code가 main repo에 적용 후 pytest tests/card5 -v 의무
- monkeypatch test 실패 시 → 알고리즘팀 fallback 패턴 추가 의무
- str() 캐스팅 누락 회귀 시 → apply_alias 호출부 정정 의무

## 봉인 본문 (변경 0건)
- adapter_sha=5b7806bdfece1b4cee61486998a0396194562da459e23aaa2094d55474d72135
- real_transactions_v2_sha=949b1e0072345ae73dd31ff89a3b4b4945184942ac26ac77403d66b3f96b3b57
- canonical_alias_map_sha=4a8c2b38999968a83515e6f80cc12c660d767801ea72e012254de1a0d24ad615
- retraining=false
- adapter_changed=false
- model_weight_changed=false
