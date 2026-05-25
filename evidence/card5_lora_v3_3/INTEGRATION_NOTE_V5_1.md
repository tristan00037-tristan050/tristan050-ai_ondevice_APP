# Card 5 v3.3 Option D — V5.1 Integrated Package

## 작업 본질
DEFECT_1 잔여 결함 정정 hotfix. manifest_resolver.py 상대경로 중복 결합 차단.

## Source
- Codex v5.1 zip SHA: 559db707b26df3eea4e4fa3494066bb3ead450b9f763928bedf03c637fcfc6f4 (base)
- 알고리즘팀 v5.2 zip SHA: 2560c4c3cc01e0ad4227fc2afb279af08e1c3c864d3f5ee951afb9228659d1a9 (evidence supplement)

## 통합 결정 (총괄기획팀)

### Codex v5.1 채택 사유
1. 보완팀 수정개발지시서 본문 완전 정합 (manifest_resolver.py + 5건 회귀 test)
2. 새 폴더 명칭 rework_v5_1 (작업 명칭 명확)
3. ALGORITHM_TEAM_REPLY_V5_1.md 회신본 포함
4. PACKAGE_SHA256SUMS.txt 포함
5. v5 통합본의 신규 모듈 5개 유지 (adapter_loader, invariants, rollback, system_prompt, allowlist)

### 알고리즘팀 v5.2 보강 본문 (evidence만 추가)
- evidence/accounting27/rework_v5_1_verification.{json,txt}
- evidence/accounting27/rework_v5_verification.{json,txt}
- evidence/accounting27/rework_v4_verification.{json,txt}
- evidence/accounting27/rework_v2_verification.{json,txt}
- evidence/accounting27/rework_v2_summary.json
- evidence/card5_lora_v3_3/original_v3_3_metrics.json

## 두 본문 비교 정직 표명

| 본문 | Codex | 알고리즘팀 |
|---|---|---|
| manifest_resolver.py 보완팀 정합 | ✅ | ✅ (+ fail_class + searched= 본문) |
| 5건 회귀 test 보완팀 정합 | ✅ | ✅ (+ DRY 헬퍼) |
| 신규 모듈 5개 분리 | ✅ | ❌ |
| evidence 본문 풍부 | ❌ | ✅ |

## DEFECT_1 정정 본문
- repo_root 함수 시작 시 절대경로화 (.expanduser().resolve())
- explicit/env relative path는 root / candidate로 한 번만 결합
- evidence 후보는 상대경로만 보관
- package fallback은 별도 absolute (root와 결합 0건)
- repo/repo/... 중복 차단

## 봉인 본문 (변경 0건)
- adapter_sha=5b7806bdfece1b4cee61486998a0396194562da459e23aaa2094d55474d72135
- real_transactions_v2_sha=949b1e0072345ae73dd31ff89a3b4b4945184942ac26ac77403d66b3f96b3b57
- canonical_alias_map_sha=4a8c2b38999968a83515e6f80cc12c660d767801ea72e012254de1a0d24ad615
- retraining=false
- adapter_changed=false
- model_weight_changed=false
- raw_metric_changed=false
- alias_map_semantics_changed=false
