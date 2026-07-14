# 계약 파일 병합 — v2.8.0 베이스 + v2.8.1 (메인개발팀4)

이 디렉터리는 **메인개발팀4 v2.8.1 통합 결과물**의 스키마·정책 계약 템플릿(json)과
매트릭스(csv)를 알고리즘개발팀12 v2.8.0 베이스 하네스에 병합한 결과입니다.

## 우선순위 규칙 (중복 시 v2.8.1 우선)

동일 계약이 베이스(`../policy/`, `../schemas/`)와 여기(`v2.8.1/`) 양쪽에 존재하면
**`contracts/v2.8.1/`(v2.8.1)가 권위 계약**입니다. M3 실측 시 정책·신뢰 해석은
이 디렉터리의 값을 기준으로 pinning 합니다.

| 계약 | 베이스 v2.8.0 | v2.8.1(권위) |
|------|---------------|--------------|
| benchmark policy | `policy/benchmark_policy.template.json` | `v2.8.1/benchmark_policy.model_tier_b.v2.8.1.template.json` |
| scanner policy | `policy/scanner_policy.template.json` | `v2.8.1/scanner_policy.model_tier_b.v2.8.1.template.json` |
| trust policy | `policy/trust_policy.template.json` | `v2.8.1/trust_policy.model_tier_b.v2.8.1.template.json` |
| artifact profile schema | `schemas/artifact_profile.schema.json` | `v2.8.1/artifact_profile_v2_8_1.schema.json` |
| final status schema | `schemas/final_status.schema.json` | `v2.8.1/final_status_v2_8_1.schema.json` |
| acceptance / attack matrix, defect traceability | `spec/v2.8/02_구현계약/*.csv` | `v2.8.1/*.csv` |

## 베이스 실행 코드 계약(schema_version 문자열)은 미변경

베이스 하네스 코드·테스트는 `...v2.8` schema_version 문자열에 결속되어 있어,
계약 병합이 실행 코드 계약을 깨지 않도록 **베이스 `policy/`·`schemas/` 원본은 보존**하고
v2.8.1 계약을 이 디렉터리에 별도 배치했습니다. 정책 값 확정(UNSET→운영값)과 digest
pinning은 M3 실측 단계(머지 후 대표)에서 수행합니다. 현재 모든 정책값은 `UNSET`/`0`
DRAFT 상태이며, 이는 `RUNTIME_ACTIVATION_ALLOWED=0` fail-closed 불변과 일치합니다.
