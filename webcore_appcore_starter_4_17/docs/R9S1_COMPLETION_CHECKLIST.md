# R9-S1 완료 체크리스트

## 완료된 작업 요약

### 1. CS 도메인 v1 구현

#### 데이터베이스
- ✅ `011_cs_tickets.sql` 마이그레이션 파일 생성
- ✅ `cs_tickets` 테이블 + 인덱스 `(tenant, created_at, status)`

#### Service Core
- ✅ `service-core-cs` 패키지 구현
- ✅ `listTickets()` - 필터 + 페이징
- ✅ `summarizeTickets()` - 상태별 카운트
- ✅ `csTickets.test.ts` - 단위 테스트

### 2. App (CsHUD ↔ BFF)

#### API 클라이언트
- ✅ `cs-api.ts` 구현
  - Mock 모드: 네트워크 0 + 더미 데이터
  - Live 모드: `/v1/cs/tickets` 호출

#### UI
- ✅ `CsHUD.tsx` 구현
  - `useEffect`로 CS 티켓 로딩
  - 로딩/에러/빈 상태 처리
  - `subject` / `status` / `createdAt` 리스트 렌더링

### 3. BFF (Backend for Frontend)

#### 라우트
- ✅ `routes/cs-tickets.ts` - `GET /v1/cs/tickets`
  - `requireTenantAuth`, `requireRole('operator')`
  - `status`, `limit`, `offset` 쿼리 지원
  - `listTickets()` 호출, `{ items: CsTicket[] }` 응답

- ✅ `routes/cs-os-dashboard.ts` - CS 요약용 OS Dashboard 라우트

#### 테스트
- ✅ `cs-tickets-guards.test.mjs`
  - 인증/권한/파라미터 가드 테스트

### 4. Web (OS Dashboard)

- ✅ `OsDashboard.tsx` CS Tickets 카드
  - Open / Pending / Closed 카운트 표시
  - 기존 Accounting 카드와 동일 스타일

### 5. Test

#### E2E 테스트
- ✅ `mock-no-network.spec.mjs` 확장
  - CS HUD 탭 전환까지 포함하는 Mock 네트워크 0 시나리오

#### BFF 테스트
- ✅ `/v1/cs/tickets` 인증 없음 → 401/403
- ✅ `viewer` role → 403
- ✅ 정상 헤더 → 200 + `items[]` 스키마 검증
- ✅ `status`, `limit`, `offset` 파라미터 검증

### 6. 문서

- ✅ `DEMO_15MIN_SCRIPT.md` - Export 스모크 테스트 Step 추가
- ✅ `PILOT_ENV_SETUP.md` - `EXPORT_SIGN_SECRET` 환경 변수 추가
- ✅ `R9S2_SPRINT_BRIEF.md` - R9-S2 스프린트 브리프 생성
- ✅ `R9S2_TICKETS.md` - R9-S2 티켓 문서 생성

### 7. 환경 설정

- ✅ `.env` 파일에 `EXPORT_SIGN_SECRET=dev-export-secret` 추가
- ✅ BFF 서버 재기동 완료 (`/healthz` OK)

---

## R9-S1 종료 절차

### Step 1: GitHub PR 생성 및 머지

**PR 정보:**
- Base: `main`
- Compare: `r9-s1-cs-v1`
- 제목: `feat(r9-s1): CS tickets v1 domain + HUD/BFF/OS integration`
- Merge 전략: **Squash and merge**

**PR 본문:**
```
- S-09-1: cs_tickets, service-core-cs, csTickets tests
- A-10-1: CsHUD ↔ /v1/cs/tickets 연동, Mock 네트워크 0 유지
- S-09-2: BFF /v1/cs/tickets + 가드 테스트
- T-03: Mock-0 E2E 확장, BFF role/파라미터 테스트
- W-10: OS Dashboard CS Tickets 카드 + /v1/cs/os/dashboard
```

### Step 2: 태그 생성 (PR 머지 후)

```bash
cd webcore_appcore_starter_4_17
git checkout main
git pull origin main

git tag r9-s1-done-20251210
git push origin --tags
```

이 태그가 **"CS 도메인 v1 + HUD/BFF/OS/테스트 기준선"**이 됩니다.

### Step 3: 수동 QA 최종 체크

#### 1) App – Mock 모드 (네트워크 0 확인)
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:mock
```
- Accounting HUD → CS HUD로 탭 전환
- 브라우저/DevTools Network 탭에서 HTTP/WS 요청 0건 유지 확인

#### 2) App – Live 모드 + CS HUD
```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:live
```
- CS HUD 탭 진입
- 티켓 리스트가 로드되고, `status` / `subject` / `createdAt`이 표시되는지 확인

#### 3) OS Dashboard – CS 카드
- `http://localhost:5173/os/dashboard` 접속
- CS 카드에서 Open / Pending / Closed 값 표시 확인
- 데이터가 없을 때도 카드 레이아웃이 무너지지 않는지 확인

#### 4) (선택) Accounting Export 스모크 테스트
- 같은 Live 모드에서 Accounting HUD Export 버튼 1회 클릭
- 이전의 `500 missing_export_sign_secret`가 아닌
- 정상 응답, 또는 정의된 에러 UX(예: "준비 중입니다")로 처리되는지 확인

---

## 다음 스프린트: R9-S2

R9-S1 완료 후 바로 R9-S2를 시작할 수 있습니다.

**R9-S2 목표:** CS 도메인에 온디바이스 LLM 연동 (상담 요약/응답 추천)

**준비된 문서:**
- `docs/R9S2_SPRINT_BRIEF.md`
- `docs/R9S2_TICKETS.md`

**브랜치 생성:**
```bash
cd webcore_appcore_starter_4_17
git checkout main
git pull origin main
git switch -c r9-s2-cs-llm
git push -u origin r9-s2-cs-llm
```

