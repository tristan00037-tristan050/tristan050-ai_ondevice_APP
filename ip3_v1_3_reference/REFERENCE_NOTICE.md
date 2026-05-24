# ip3_v1_3_reference — Standalone Reference Package

본 디렉토리는 그룹 A (기술개발 마스터팀2)가 SEALED 봉인한 IP3 v1.3 Full-Stack Reference Architecture 패키지입니다.

## 본 디렉토리 본문 (Butler 앱과 분리)

- standalone reference architecture (Butler 앱 runtime 통합 0건)
- 14 Python 모듈 (`src/ip3/`) — CI/local self-check 본문
- 24 gate runner (`tools/`)
- 4 unit tests (`tests/`)
- 8 CI/local 스크립트 (`scripts/ops/`)
- 3 PowerShell Windows collectors (`windows/`)
- 9 markdown 문서 (`docs/`)
- 6 sample_replay JSON (`evidence/`)
- types wrapper schema (`schema/ip3_routing_contract.schema.json`)
- 2 GitHub Actions workflow (`.github/workflows/`)

## 봉인 본문

- zip SHA: `4a6b534b3b474fccbafe42d9df274ffbb03beff93bf3fc24ecd1be56e935d4cd`
- 원본 zip: `Butler_IP3_OnDevice_Context_Routing_Engine_v1_3_FULL_STACK_WORLD_CLASS_SEALABLE_DEV_PACK.zip`
- 인계일: 2026-05-23
- 인계 그룹: 기술개발 마스터팀2 (그룹 A) → 6팀 그룹 (총괄기획팀 경유)
- 본 PR: #752 (옵션 3 Hybrid Architecture 적용, 대표 결정 2026-05-23)

## 본 디렉토리 수정 금지

- 그룹 A SEALED 본문 영구 보존 의무
- 향후 zip 갱신 시 디렉토리 전체 교체만 허용 (부분 수정 0건)
- 본 디렉토리 schema는 Butler runtime의 `butler_pc_core/ip3/schema/` 본문과 다름 (의도된 차이)

## Butler runtime 통합 본문

- Butler 앱 runtime 통합 = `butler_pc_core/ip3/` (별도, flat schema, Python collectors)
- 본 디렉토리 = CI 검증 / seal handoff / local self-check 본문만
- 향후 IP1 v5.4 forward evidence + IP2 v2.4 live PEP 통합 시 adapter layer (`butler_pc_core/ip3/reference_bridge.py` 신규) 추가 검토 의무

## 본질 차이 본질 (Butler runtime vs reference)

| 본질 | Butler runtime (`butler_pc_core/ip3/`) | reference (본 디렉토리) |
|---|---|---|
| schema 구조 | flat (default_decision, routing_targets 등 top-level) | `types` wrapper (DeviceTelemetry, DeviceClass, UserContext) |
| schema_version | `ip3.evidence_class_taxonomy.v1` | `ip3.evidence_taxonomy.v1.3.2` |
| approval_matrix | JSON 본질 | markdown 본질만 (`docs/IP3_V1_3_APPROVAL_MATRIX.md`) |
| telemetry 본질 | `base.py` + `{os}_collector.py` (Python per-OS) | `telemetry_schema.py` 단일 + `windows/*.ps1` PowerShell |

위 차이는 의도된 본질 (Butler runtime 통합 vs reference CI 검증의 별개 목적). 향후 단계에서 adapter 본질로 연결 가능.

## 차단 본질 영구 (zip README + Butler 정합)

- `production_hook_deployed=true` 차단
- `release_claim_allowed=false` 봉인
- `APPROVED_FOR_PRODUCTION` 0건
- `APPROVED_FOR_PHYSICAL_WINDOWS_LAB` 0건 (실제 Windows 노트북 0건 상태)
- `local_1_7b_forward_verified=true` 차단 (IP1 v5.4 forward evidence 0건)
- live bridge deployment 0건 (IP2 v2.4 live PEP evidence 0건)
- 단조 정책 (`ci_lab < vm_lab < physical_lab < production`) 단조 위반 claim 0건
