# R6 회계 스모크 테스트 가이드

## 🚀 빠른 시작

### 1. BFF Accounting 서버 실행

```bash
# BFF Accounting 디렉토리로 이동
cd packages/bff-accounting

# 의존성 설치 (처음 한 번만)
npm install

# 개발 모드로 서버 실행
npm run dev
```

서버가 `http://localhost:8081`에서 실행됩니다.

---

### 2. 스모크 테스트 실행

**터미널 1**: BFF 서버 실행 중 유지

**터미널 2**: 스모크 테스트 실행

```bash
# 루트 디렉토리에서
npm run smoke:accounting
```

또는 환경 변수 설정 후:

```bash
export BFF_URL="http://localhost:8081"
export API_KEY="collector-key"
export TENANT_ID="default"
bash scripts/smoke_accounting.sh
```

---

## 📋 테스트 항목

스모크 테스트는 다음 API를 순차적으로 테스트합니다:

1. **분개 추천** (`POST /v1/accounting/postings/suggest`)
   - 라인아이템 → 분개 추천
   - 신뢰도 및 근거 확인

2. **분개 생성** (`POST /v1/accounting/postings`)
   - 추천된 분개를 실제로 생성
   - Idempotency-Key 처리

3. **승인 요청** (`POST /v1/accounting/approvals`)
   - 분개에 대한 승인 요청 생성

4. **승인 상태 조회** (`GET /v1/accounting/approvals/:id`)
   - 승인 상태 확인

5. **Export 요청** (`POST /v1/accounting/exports`)
   - 감사용 Export 요청

---

## 🔧 문제 해결

### 서버가 실행되지 않음

```bash
# 포트 확인
lsof -i :8081

# 포트가 사용 중이면 프로세스 종료
kill -9 <PID>

# 또는 다른 포트 사용
PORT=8082 npm run dev
export BFF_URL="http://localhost:8082"
npm run smoke:accounting
```

### 연결 오류 (Connection refused)

- BFF 서버가 실행 중인지 확인
- `BFF_URL` 환경 변수가 올바른지 확인 (기본값: `http://localhost:8081`)

### 404 Not Found

- BFF 서버의 라우트가 제대로 등록되었는지 확인
- `packages/bff-accounting/src/index.ts`에서 `suggestRouter`가 등록되었는지 확인

### 422 Validation Error

- 요청 본문이 OpenAPI 스키마와 일치하는지 확인
- Ajv 검증 오류 메시지 확인

---

## 📊 예상 결과

성공 시:

```
==========================================
Test Summary
==========================================
Passed: 5
Failed: 0

✅ All tests passed!
```

실패 시:

```
==========================================
Test Summary
==========================================
Passed: 2
Failed: 3

❌ Some tests failed!
```

---

## 🔍 상세 로그

스모크 테스트는 각 단계별로 상세한 로그를 출력합니다:

- ✅ PASS: 테스트 통과
- ❌ FAIL: 테스트 실패 (HTTP 상태 코드 및 응답 본문 포함)
- ℹ️  INFO: 정보 메시지 (스킵된 테스트 등)

---

## BFF E2E 스모크 (suggest)

### 실행

```bash
# 터미널 1
cd packages/bff-accounting
npm install
npm run dev   # http://localhost:8081/health

# 터미널 2 (repo root)
export BFF_URL="http://localhost:8081"
export API_KEY="collector-key"
export TENANT_ID="default"
npm run test:e2e:accounting:bff
```

### 통과 기준

- HTTP 200
- body.postings: array
- body.confidence: number|string
- body.rationale: string

### 전체 스모크 실행

```bash
# 모든 회계 스모크 테스트 실행 (기존 smoke + BFF E2E)
npm run smoke:accounting:all
```

---

## 📚 참고

- `scripts/smoke_accounting.sh` - 스모크 테스트 스크립트
- `tests/accounting_e2e_bff.mjs` - BFF E2E 스모크 테스트
- `packages/bff-accounting/src/routes/suggest.ts` - 분개 추천 라우트
- `contracts/accounting.openapi.yaml` - API 명세

