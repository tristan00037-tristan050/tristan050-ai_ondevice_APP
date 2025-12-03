# R6 Self Check – 3 Commands

## 1) 계약/타입/스키마

```bash
npm run ci:gen-types:accounting
npm run ci:validate:accounting
```

## 2) 금지 규칙

```bash
npm run ci:check-client-filter
npm run ci:check-roles
```

## 3) 스모크

```bash
npm run smoke:accounting
```

> 위 3개 축 모두 통과해야 PR 머지 가능.

---

## 상세 설명

아래는 원래 상세 가이드입니다.

---

## 1️⃣ 계약/타입/스키마 일관성

```bash
npm run ci:gen-types:accounting && npm run ci:validate:accounting
```

**검증 항목**:
- ✅ OpenAPI → TypeScript 타입 생성
- ✅ Ajv 스키마 검증 (ledger_posting, export_manifest)
- ✅ 타입/스키마 동기화 확인

**예상 결과**:
- 타입 생성 성공: `packages/bff-accounting/src/types/accounting.ts`
- 스키마 검증 통과: 골든셋 데이터 검증 성공

---

## 2️⃣ 금지 규칙 가드

```bash
npm run ci:check-client-filter && npm run ci:check-roles
```

**검증 항목**:
- ✅ 클라이언트 측 필터/집계 금지 (`useMemo` with `filter` 감지)
- ✅ 역할 가드 누락 차단 (`requireTenantAuth`, `requireRole` 누락 감지)

**예상 결과**:
- 클라이언트 필터 금지: 통과 (서버사이드 필터만 사용)
- 역할 가드: 통과 (모든 보호된 경로에 가드 적용)

---

## 3️⃣ 스모크 테스트

```bash
scripts/smoke_accounting.sh
```

**검증 항목**:
- ✅ 분개 추천 API (`POST /v1/accounting/postings/suggest`)
- ✅ 분개 생성 API (`POST /v1/accounting/postings`)
- ✅ 승인 요청 API (`POST /v1/accounting/approvals`)
- ✅ 승인 상태 조회 API (`GET /v1/accounting/approvals/:id`)
- ✅ Export 요청 API (`POST /v1/accounting/exports`)

**사전 요구사항**:
- BFF Accounting 서버 실행 중 (`packages/bff-accounting`)
- 환경 변수 설정:
  ```bash
  export BFF_URL="http://localhost:8081"
  export API_KEY="collector-key"
  export TENANT_ID="default"
  ```

**예상 결과**:
- 모든 API 호출 성공 (200/201/202)
- 테스트 카운터: Passed > 0, Failed = 0

---

## 📋 전체 검증 (한 번에 실행)

```bash
# 1) 계약/타입/스키마 일관성
npm run ci:gen-types:accounting && npm run ci:validate:accounting

# 2) 금지 규칙 가드
npm run ci:check-client-filter && npm run ci:check-roles

# 3) 스모크 테스트 (BFF 서버 실행 후)
scripts/smoke_accounting.sh
```

---

## 🔍 상세 검증 항목

### 계약 우선 원칙

- ✅ OpenAPI 명세 → TypeScript 타입 자동 생성
- ✅ Ajv 스키마 검증 (런타임 + CI)
- ✅ 타입/스키마 불일치 시 CI 실패

### 서버사이드 필터/집계

- ✅ 클라이언트 측 `useMemo` with `filter` 금지
- ✅ 모든 필터링/페이지네이션은 서버에서 처리
- ✅ CI 게이트: `check_client_filter.mjs`

### 테넌트 격리 + 역할 가드

- ✅ 모든 보호된 경로에 `requireTenantAuth` 적용
- ✅ 관리자 경로에 `requireRole('admin')` 적용
- ✅ CI 게이트: `check_roles_guard.mjs`

### 금액/통화 표현

- ✅ 금액: `string` 타입 (부동소수점 오류 방지)
- ✅ 통화: ISO-4217 코드 강제 (`pattern: "^[A-Z]{3}$"`)
- ✅ OpenAPI/Ajv 스키마에 반영

### 멱등성

- ✅ `Idempotency-Key` 헤더 지원
- ✅ `client_request_id` 필드 지원
- ✅ OpenAPI 명세에 명시

---

## 🚨 실패 시 조치

### 타입 생성 실패

```bash
# openapi-typescript 설치 확인
npm install -D openapi-typescript

# 수동 타입 생성
npx openapi-typescript contracts/accounting.openapi.yaml -o packages/bff-accounting/src/types/accounting.ts
```

### 스키마 검증 실패

```bash
# 골든셋 데이터 확인
cat datasets/gold/ledgers.json

# 스키마 수동 검증
node scripts/validate_accounting.js --posting datasets/gold/ledgers.json
```

### 클라이언트 필터 감지

```bash
# 감지된 파일 확인
npm run ci:check-client-filter

# 서버사이드 필터로 변경
# useMemo 제거, API 호출 시 query parameter 사용
```

### 역할 가드 누락

```bash
# 감지된 경로 확인
npm run ci:check-roles

# 누락된 경로에 requireTenantAuth/requireRole 추가
```

---

## 📚 참고 문서

- `docs/R6_ACCOUNTING_KICKOFF.md` - 킥오프 문서
- `docs/accounting/CF_BENCHMARK_MATRIX.csv` - 벤치마크 매트릭스
- `docs/accounting/UX_FLOWS.md` - UX 플로우
- `docs/accounting/SECURITY_MAPPING.md` - 보안 매핑
- `contracts/accounting.openapi.yaml` - OpenAPI 명세
- `contracts/ledger_posting.schema.json` - 분개 스키마

---

## ✅ 체크리스트

- [ ] 계약/타입/스키마 일관성 검증 통과
- [ ] 금지 규칙 가드 검증 통과
- [ ] 스모크 테스트 통과
- [ ] CI 워크플로우 통과 (GitHub Actions)

---

**마지막 업데이트**: R6 킥오프 완료 시점

