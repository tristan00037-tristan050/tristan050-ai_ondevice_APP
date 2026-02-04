# R6 회계 확장 킥오프

R5d~5.4 기준선을 계승한 회계 도메인 확장 킥오프 문서입니다.

## 🎯 목표

캠프파이어 벤치마킹 + 우리 플랫폼 표준(계약 우선/서버사이드/테넌트 격리)을 모두 충족하는 회계 기능 구현

---

## 📋 구현 완료 (즉시 실행 체크리스트 F)

### ✅ 1. 디렉터리/파일 스캐폴딩

**생성된 디렉터리**:
- `docs/accounting/` - 회계 문서
- `contracts/` - OpenAPI 및 Ajv 스키마
- `packages/service-core-accounting/` - 규칙 DSL/추천/검증
- `packages/bff-accounting/` - Express 라우트
- `packages/app-expo/modules/accounting/` - RN 모듈
- `tests/` - E2E 테스트
- `datasets/receipts/` - 영수증 이미지
- `datasets/gold/` - 골든셋

### ✅ 2. 계약/스키마 파일

**생성된 파일**:
- `contracts/accounting.openapi.yaml` - 회계 API OpenAPI 명세
- `contracts/ledger_posting.schema.json` - 분개 JSON Ajv 스키마
- `contracts/export_manifest.schema.json` - Export 매니페스트 스키마

**주요 특징**:
- 금액 표현: `string` 타입 (부동소수점 오류 방지)
- 통화: ISO-4217 코드 강제 (`pattern: "^[A-Z]{3}$"`)
- 상태: `enum` 사용 (pending/approved/rejected/needs_review)
- 멱등성: `Idempotency-Key` 헤더 및 `client_request_id` 필드
- 에러 응답: 401/403/422/429 명시

### ✅ 3. 회계용 레드랙션 룰

**생성된 파일**:
- `redact/redact_rules.accounting.json` - 회계 전용 레드랙션 규칙

**포함된 규칙**:
- 계좌번호 마스킹
- 카드번호 마스킹
- 사업자등록번호 마스킹
- 세금번호 마스킹
- 이메일 마스킹
- 전화번호 마스킹
- 상세 주소 마스킹

### ✅ 4. 스모크 스크립트

**생성된 파일**:
- `scripts/smoke_accounting.sh` - 회계 스모크 테스트
- `tests/accounting_e2e.mjs` - E2E 테스트 래퍼

**테스트 항목**:
- 분개 추천
- 분개 생성
- 승인 요청
- 승인 상태 조회
- Export 요청

### ✅ 5. CI 게이트 연결

**추가된 스크립트**:
- `scripts/validate_accounting.js` - 회계 스키마 검증
- `scripts/generate-accounting-types.sh` - 회계 OpenAPI 타입 생성

**package.json 스크립트**:
- `ci:validate:accounting` - 회계 스키마 검증
- `ci:gen-types:accounting` - 회계 타입 생성
- `smoke:accounting` - 회계 스모크 테스트

**CI 워크플로우 업데이트**:
- `schema-validation` job에 회계 스키마 검증 추가
- `openapi-sync` job에 회계 타입 생성 추가
- `test` job에 회계 스모크 테스트 추가

### ✅ 6. 알림 규칙

**추가된 함수**:
- `notifyAccountingBlockSpike()` - 회계 Block 스파이크 알림

**Dedup 키**: `tenant + accounting_block_spike + window`

**문서 업데이트**:
- `docs/OBSERVABILITY_DASHBOARD_NOTES.md`에 회계 Block 스파이크 알림 추가

### ✅ 7. 벤치마크 문서

**생성된 파일**:
- `docs/accounting/CF_BENCHMARK_MATRIX.csv` - 기능 등가성 표
- `docs/accounting/UX_FLOWS.md` - UX 플로우
- `docs/accounting/SECURITY_MAPPING.md` - 보안 매핑
- `docs/accounting/CF_KPI_BASELINE.md` - KPI 정의/측정법

---

## 🔒 검토팀 P0 요구사항 반영

### ✅ 금액/통화 표현

- **금액**: `string` 타입, 패턴 검증 (`^-?[0-9]+(\.[0-9]{1,2})?$`)
- **통화**: ISO-4217 코드 강제 (`pattern: "^[A-Z]{3}$"`)
- **OpenAPI/Ajv 스키마에 반영 완료**

### ✅ 멱등성

- **Idempotency-Key 헤더**: `/v1/accounting/postings` 엔드포인트
- **client_request_id 필드**: `CreatePostingRequest` 스키마
- **향후 구현 시 적용 예정**

### ✅ 회계 PII 레드랙션/보존 정책

- **레드랙션 규칙**: `redact/redact_rules.accounting.json`
- **보안 매핑**: `docs/accounting/SECURITY_MAPPING.md`
- **암호화 정책**: 저장 시 AES-256-GCM, Export 시 레드랙션

---

## 📊 기준선 정합성

R5d~5.4 기준선을 그대로 계승:

- ✅ 서버사이드 필터/페이지네이션
- ✅ 테넌트 격리
- ✅ 역할 가드 (viewer/operator/auditor/admin)
- ✅ 키/토큰 비영구화
- ✅ ETag/304 캐싱
- ✅ 지터/백오프
- ✅ Ajv 풀 검증
- ✅ OpenAPI→타입 동기화

---

## 🚀 다음 단계 (R6-S1)

### 주 1-2 작업

1. **계약/스키마 확정**
   - OpenAPI 명세 검토 및 확정
   - Ajv 스키마 검증 테스트

2. **규칙 DSL v0 구현**
   - 기본 연산자 (>, ≥, 매핑, 클램프)
   - 분개 추천 v0 (신뢰도·근거 문자열)

3. **골든셋 v0 구성**
   - ≥50건 골든셋 구성
   - 정확도 리포트 스크립트

---

## 📚 참고 문서

- `docs/accounting/CF_BENCHMARK_MATRIX.csv` - 기능 등가성 표
- `docs/accounting/UX_FLOWS.md` - UX 플로우
- `docs/accounting/SECURITY_MAPPING.md` - 보안 매핑
- `docs/accounting/CF_KPI_BASELINE.md` - KPI 정의
- `contracts/accounting.openapi.yaml` - OpenAPI 명세
- `contracts/ledger_posting.schema.json` - 분개 스키마
- `contracts/export_manifest.schema.json` - Export 매니페스트 스키마

---

## ✅ 체크리스트

- [x] 디렉터리/파일 스캐폴딩 생성
- [x] 계약/스키마 파일 생성
- [x] 회계용 레드랙션 룰 강화
- [x] 스모크 스크립트 등록
- [x] CI 게이트 연결
- [x] 알림 규칙 추가
- [x] 벤치마크 문서 생성

---

**검토팀 승인**: Proceed (집행 승인) ✅

**다음 단계**: R6-S1 스프린트 시작 (주 1-2)


