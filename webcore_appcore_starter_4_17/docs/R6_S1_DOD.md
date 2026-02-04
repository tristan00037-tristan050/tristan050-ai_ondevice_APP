# R6-S1 DoD (회계 – 스프린트 1)

## 기능

- 규칙 DSL v0 (>, >=, <, <=, ==, != / 매핑 / 클램프)
- 분개 추천(suggest) + 신뢰도 + 근거 문자열 + 대차 균형

## 데이터

- 골든셋 ≥ 50건 (datasets/gold/ledgers.json)

## 품질 측정

- `npm run measure:accuracy` 수치 출력
- CI 게이트: `npm run ci:bench:accounting`
  - 임계치: TOP-1 ≥ 70%, TOP-5 ≥ 85%

## 통합/E2E

- `/v1/accounting/postings/suggest` E2E: `npm run test:e2e:accounting`
- 스모크: `npm run smoke:accounting`

## 금지/가드(상수)

- 클라이언트 필터/집계 금지 (CI)
- requireTenantAuth + 역할 가드 (CI)
- OpenAPI→타입→Ajv 스키마 계약 우선 (CI)

## CI Gate (필수)

- 골든셋 개수: `npm run ci:gold-size` (≥50, PII 금지)
- 정확도 임계치: `npm run ci:bench:accounting` (TOP-1≥70, TOP-5≥85)
- E2E: `npm run smoke:accounting:all`

### 데이터 품질 게이트 (CI 고정)

- 골든셋 ≥ 50 (PII 무유출, 형식 검증 통과)
- 합성 보조 케이스 비율 ≤ 30% (gold_enforce_ratio 게이트)
- 정확도 하한선: Top‑1 ≥ 70%, Top‑5 ≥ 85% (CI 게이트로 강제)
- CI 순서: schema-and-types → golden-set-guard → **ci:gate:accuracy** → e2e-bff-accounting

### Top‑5 개선 가이드

- 후보 확장(topn.ts)으로 Top‑N 대안 품질 개선 (Top‑1 로직 불변)
- 정확도 하한선: Top‑1 ≥ 70%, Top‑5 ≥ 85% (CI 게이트로 강제)
- 합성 보조 케이스 비율 ≤ 30% (gold_enforce_ratio 게이트)

> 위 조건 모두 충족 시 R6-S1 완료로 간주.

