# R9-S1 스프린트 개별 티켓

이 문서의 티켓들은 Jira/Linear/노션 등에 바로 복사하여 사용할 수 있습니다.

---

## 0. 공통 · 스프린트 준비 티켓

### [R9S1-00] R9-S1 브랜치 생성 및 공통 스프린트 세팅

**설명**

R9-S1 스프린트용 브랜치 생성 및 기본 환경 세팅

기준선/원칙을 레포/보드에 명시

**할 일**

- `git checkout main && git pull`
- `git tag r8-s2-done-20251209` 확인
- `git switch -c r9-s1-cs-v1`
- `docs/R9S1_SPRINT_BRIEF.md`, `R9S1_DETAILED_TASKS.md` 스프린트 위키에 링크
- 보드 컬럼/레이블 세팅 (예: `domain:cs`, `type:web/app/server/test`)

**Acceptance Criteria**

- [ ] `r9-s1-cs-v1` 브랜치 생성 및 원격에 푸시
- [ ] 스프린트 보드에 R9-S1용 필터/레이블 세팅
- [ ] 스프린트 설명에 "CS 도메인 v1 기능 + 엔진 계층 멀티 도메인 재사용 검증" 원칙 명시
- [ ] "회계/OS/HUD 코어 구조 변경 금지" 원칙 명시

**우선순위**: P0

**의존성**: 없음

---

## 1. Web (W-10) 티켓

### [R9S1-W10-1] CS OS Dashboard 지표 1개 구현

**설명**

OS Dashboard의 CS 카드에 실제 데이터 1개(`daily_new_tickets`)를 표시하여 "CS 도메인이 동작한다"는 것을 증명

**할 일**

- CS OS Dashboard API 응답 구조 정의 (`CsOsDashboardResponse` 타입)
- OS Dashboard CS 카드에 실제 API 호출 연동
- 에러 처리 (API 호출 실패 시 폴백 UI)
- Demo 모드 안내 문구

**Acceptance Criteria**

- [ ] OS Dashboard에서 CS 카드가 실제 API를 호출함
- [ ] `daily_new_tickets` 값이 정상적으로 표시됨
- [ ] API 호출 실패 시 적절한 폴백 UI 표시
- [ ] 회계 카드 레이아웃/기능에 영향 없음

**참고 파일**

- `packages/ops-console/src/pages/os/OsDashboard.tsx`
- `packages/ops-console/src/types/cs.ts` (신규)
- `packages/ops-console/src/api/cs.ts` (신규)

**우선순위**: P0

**의존성**: [R9S1-S09-2] CS OS Dashboard API 구현

---

### [R9S1-W10-2] CS 메뉴/라우트 운영용 구조 정리

**설명**

CS 도메인을 위한 최소한의 메뉴/라우트 구조를 정리하여 향후 확장 가능하게 만듦

**할 일**

- CS Overview 페이지를 실제 동작하는 페이지로 업그레이드
- 최소 기능: "최근 티켓 목록" 또는 "CS 요약" 표시
- 라우트 구조 정리 (`/cs`, `/cs/tickets` 등)
- 네비게이션 개선 (OS Dashboard CS 카드 → `/cs` 이동)

**Acceptance Criteria**

- [ ] `/cs` 경로로 접근 시 실제 데이터가 표시됨
- [ ] CS 메뉴가 사이드바에 표시되고 정상 동작함
- [ ] OS Dashboard CS 카드 클릭 시 `/cs`로 이동
- [ ] 회계 관련 메뉴/라우트에 영향 없음

**참고 파일**

- `packages/ops-console/src/pages/cs/CSOverview.tsx`
- `packages/ops-console/src/App.tsx`

**우선순위**: P1

**의존성**: [R9S1-S09-1] CS 도메인 로직 구현

---

## 2. App (A-10) 티켓

### [R9S1-A10-1] CsHUD 티켓 리스트 + 요약 실제 API 연동

**설명**

CsHUD에서 더미 데이터 대신 실제 BFF API를 호출하여 티켓 리스트와 요약을 표시

**할 일**

- CS API 클라이언트 구현 (`getCsTickets`, `getCsSummary`)
- CsHUD UI 업그레이드 (티켓 리스트, 요약 표시)
- Mock/Live 모드 분기 (Mock: 더미 데이터, Live: 실제 API)
- 로딩 상태 및 에러 처리

**Acceptance Criteria**

- [ ] CsHUD에서 최근 티켓 리스트가 표시됨
- [ ] 티켓 선택 시 요약이 표시됨
- [ ] Mock 모드에서 네트워크 호출이 0건 (E2E 테스트로 검증)
- [ ] Live 모드에서 실제 BFF API 호출

**참고 파일**

- `packages/app-expo/src/ui/CsHUD.tsx`
- `packages/app-expo/src/hud/cs-api.ts` (신규)

**우선순위**: P0

**의존성**: [R9S1-S09-1] CS 도메인 로직 구현, [R9S1-S09-2] CS BFF 라우트 구현

---

### [R9S1-A10-2] CS HUD에서 EngineMode/LocalLLMEngineV1 재사용

**설명**

회계 도메인에서 만든 SuggestEngine 계층을 CS 도메인에서도 재사용하여 "도메인 공통 엔진"임을 증명

**할 일**

- CS SuggestEngine 인터페이스 정의 (`CsSuggestRequest`, `CsSuggestResponse`)
- CS SuggestEngine 구현 (`CsRuleEngineV1` 또는 `LocalRuleEngineV1Adapter` 확장)
- CsHUD에 엔진 통합 및 상태바 표시
- 엔진 모드 전환 테스트 (rule / local-llm)

**Acceptance Criteria**

- [ ] CS HUD에서 SuggestEngine을 사용하여 추천 생성
- [ ] 엔진 모드에 따라 다른 추론 경로 사용 (rule / local-llm)
- [ ] 상태바에 현재 엔진 모드 표시
- [ ] Mock 모드에서 네트워크 호출 0건 유지
- [ ] 회계 HUD의 엔진 계층과 동일한 인터페이스 사용

**참고 파일**

- `packages/app-expo/src/hud/engines/types.ts`
- `packages/app-expo/src/hud/engines/cs-suggest.ts` (신규)
- `packages/app-expo/src/hud/engines/index.ts`
- `packages/app-expo/src/ui/CsHUD.tsx`

**우선순위**: P0

**의존성**: [R9S1-A10-1] CsHUD API 연동

---

## 3. Server (S-09) 티켓

### [R9S1-S09-1] service-core-cs 도메인 로직 v1 (티켓 목록/요약)

**설명**

service-core-cs 패키지에 실제 CS 도메인 로직을 구현하여 티켓 목록 조회 및 요약 생성 기능 제공

**할 일**

- CS 티켓 데이터 모델 정의
- CS Repository 구현 (`getRecentTickets`, `getTicketById`)
- CS 요약 로직 구현 (초기: 규칙 기반, 추후 LLM 확장 가능)
- CS Audit 이벤트 정의

**Acceptance Criteria**

- [ ] `getRecentTickets()`가 실제 DB에서 티켓 목록을 조회함
- [ ] `generateSummary()`가 티켓 내용을 기반으로 요약을 생성함
- [ ] CS Audit 이벤트가 적절히 기록됨
- [ ] 회계 도메인 코드에 영향 없음

**참고 파일**

- `packages/service-core-cs/src/models/ticket.ts` (신규)
- `packages/service-core-cs/src/repositories/ticket-repository.ts` (신규)
- `packages/service-core-cs/src/services/summary-service.ts` (신규)
- `packages/service-core-cs/src/index.ts`

**우선순위**: P0

**의존성**: [R9S1-S09-3] CS 데이터베이스 스키마

---

### [R9S1-S09-2] /v1/cs/* BFF 라우트 구현 및 OS 정책 헤더 가드

**설명**

CS 도메인을 위한 BFF API 엔드포인트를 구현하고 OS 정책 가드를 적용

**할 일**

- CS BFF 라우트 구현 (`/v1/cs/tickets`, `/v1/cs/tickets/:id/summary`)
- CS OS Dashboard 라우트 구현 (`/v1/cs/os/dashboard`)
- OS 정책 가드 적용 (`requireTenantAuth`, `requireRole`)
- X-Engine-Mode 헤더 수집 (CS Suggest 호출 시)
- BFF 라우트 등록

**Acceptance Criteria**

- [ ] `/v1/cs/tickets` API가 정상 동작함
- [ ] `/v1/cs/os/dashboard` API가 실제 데이터를 반환함
- [ ] OS 정책 가드가 적용되어 인증 없이 접근 시 403 반환
- [ ] 회계 라우트에 영향 없음

**참고 파일**

- `packages/bff-accounting/src/routes/cs-tickets.ts` (신규)
- `packages/bff-accounting/src/routes/cs-os-dashboard.ts`
- `packages/bff-accounting/src/index.ts`

**우선순위**: P0

**의존성**: [R9S1-S09-1] CS 도메인 로직 구현

---

### [R9S1-S09-3] CS 데이터베이스 스키마 및 집계 뷰

**설명**

CS 도메인을 위한 최소한의 DB 스키마를 생성하고 집계 뷰를 추가

**할 일**

- CS 티켓 테이블 생성 (`cs_tickets`)
- CS Audit 이벤트 테이블/뷰 (선택: 별도 테이블 또는 `audit_events` 사용)
- CS 집계 뷰 생성 (`cs_os_summary`)

**Acceptance Criteria**

- [ ] `cs_tickets` 테이블이 생성되고 마이그레이션이 적용됨
- [ ] `cs_os_summary` 뷰가 정상 동작함
- [ ] 회계 테이블/뷰에 영향 없음

**참고 파일**

- `packages/data-pg/migrations/011_cs_tickets.sql` (신규)
- `packages/data-pg/migrations/012_cs_os_summary.sql` (신규)

**우선순위**: P0

**의존성**: 없음

---

## 4. Test (T-03) 티켓

### [R9S1-T03-1] CsHUD Mock/Live E2E 테스트

**설명**

CsHUD가 Mock 모드와 Live 모드에서 올바르게 동작하는지 E2E 테스트로 검증

**할 일**

- CsHUD Mock 모드 테스트 (네트워크 요청 0건 검증)
- CsHUD Live 모드 테스트 (실제 API 호출 확인)
- 엔진 모드 전환 테스트 (rule / local-llm)

**Acceptance Criteria**

- [ ] Mock 모드에서 네트워크 요청 0건 (회귀 테스트 통과)
- [ ] Live 모드에서 실제 API 호출 및 데이터 표시
- [ ] 엔진 모드 전환 시 올바른 엔진 사용

**참고 파일**

- `packages/app-expo/e2e/cs-hud-mock.spec.mjs` (신규)
- `packages/app-expo/e2e/cs-hud-live.spec.mjs` (신규)

**우선순위**: P1

**의존성**: [R9S1-A10-1] CsHUD API 연동, [R9S1-A10-2] CS 엔진 통합

---

### [R9S1-T03-2] CS OS Dashboard/API 가드 테스트

**설명**

CS OS Dashboard API의 스키마 및 가드를 검증

**할 일**

- CS OS Dashboard API 테스트 (200 OK, 스키마 검증)
- CS Tickets API 가드 테스트 (인증 없이 접근 시 403)
- 회계 OS Dashboard API 회귀 테스트

**Acceptance Criteria**

- [ ] CS OS Dashboard API가 올바른 스키마로 응답
- [ ] 인증 가드가 정상 동작
- [ ] 회계 OS Dashboard API 회귀 테스트 통과

**참고 파일**

- `packages/bff-accounting/test/cs-os-dashboard-guards.test.mjs` (신규)

**우선순위**: P1

**의존성**: [R9S1-S09-2] CS BFF 라우트 구현

---

## 티켓 의존성 그래프

```
[R9S1-00] 브랜치 생성
    ↓
[R9S1-S09-3] DB 스키마
    ↓
[R9S1-S09-1] CS 도메인 로직
    ↓
[R9S1-S09-2] CS BFF 라우트
    ↓
[R9S1-W10-1] CS OS Dashboard 지표
[R9S1-A10-1] CsHUD API 연동
    ↓
[R9S1-A10-2] CS 엔진 통합
    ↓
[R9S1-W10-2] CS 메뉴/라우트 정리
[R9S1-T03-1] CsHUD E2E 테스트
[R9S1-T03-2] CS API 가드 테스트
```

---

## 우선순위 요약

- **P0 (필수)**: [R9S1-00], [R9S1-S09-3], [R9S1-S09-1], [R9S1-S09-2], [R9S1-W10-1], [R9S1-A10-1], [R9S1-A10-2]
- **P1 (중요)**: [R9S1-W10-2], [R9S1-T03-1], [R9S1-T03-2]

