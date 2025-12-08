# R8-S1 스프린트 개별 티켓

이 문서의 티켓들은 Jira/Linear/노션 등에 바로 복사하여 사용할 수 있습니다.

---

## 0. 공통 · 스프린트 준비 티켓

### [R8S1-00] R8-S1 브랜치 생성 및 공통 스프린트 세팅

**설명**

R8-S1 스프린트용 브랜치 생성 및 기본 환경 세팅

기준선/원칙을 레포/보드에 명시

**할 일**

- `git checkout main && git pull`
- `git switch -c r8-s1-cs-skeleton`
- `docs/R8S1_SPRINT_BRIEF.md`, `R8S1_DETAILED_TASKS.md` 스프린트 위키에 링크
- 보드 컬럼/레이블 세팅 (예: `domain:accounting`, `domain:cs`, `type:web/app/server/test`)

**Acceptance Criteria**

- [ ] `r8-s1-cs-skeleton` 브랜치 생성 및 원격에 푸시
- [ ] 스프린트 보드에 R8-S1용 필터/레이블 세팅
- [ ] 스프린트 설명에 "회계/OS/HUD 코어 구조 변경 금지, CS=스켈레톤만" 원칙 명시

---

## 1. Web (W-08) 티켓

### [R8S1-W08-1] Web 메뉴/라우트에 CS 섹션 추가

**설명**

ops-console 사이드바 및 라우트에 CS 영역을 추가

현재는 스켈레톤 페이지만 노출 (실제 데이터 없음)

**할 일**

- ops-console 라우터 파일에서 `/cs` 섹션 라우트 추가
- 사이드바에 "CS" or "고객지원" 메뉴 추가
- 기본 페이지 컴포넌트: "CS HUD/대시보드는 R8에서 준비 중입니다 (Skeleton)" 정도의 Placeholder UI

**Acceptance Criteria**

- [ ] `/cs` 경로로 진입 시 404 없이 Skeleton 화면 렌더
- [ ] 사이드바에 CS 메뉴가 표시되고, 클릭 시 `/cs`로 이동
- [ ] 회계 관련 메뉴(`/accounting`, `/os/dashboard`, `/manual-review`)는 기존과 동일하게 동작
- [ ] 데이터 페치/실제 서비스 호출 없음 (Stub UI만)

**참고 파일**
- `packages/ops-console/src/App.tsx`
- `packages/ops-console/src/pages/cs/CSOverview.tsx` (신규)

---

### [R8S1-W08-2] OS Dashboard에 CS 카드 슬롯 추가

**설명**

`/os/dashboard` 상단/중단 어딘가에 CS 도메인용 카드 자리만 추가

값은 Stub 또는 N/A, 추후 스프린트에서 실제 지표 연동

**할 일**

- `/os/dashboard` 레이아웃 컴포넌트 수정
- "CS 응답 품질", "CS 티켓 처리 현황" 같은 카드 타이틀/툴팁 텍스트만 추가
- 값은 `--` 또는 `N/A`로 표시
- 클릭 시 `/cs`로 이동하는 링크 정도까지만 제공 (선택)

**Acceptance Criteria**

- [ ] OS Dashboard에서 CS 관련 카드가 표시되지만, 실제 API 호출 없이 Stub 값 사용
- [ ] 카드 툴팁에 "R8-S2 이후 실제 CS 지표 연동 예정" 등 설명 문구 포함
- [ ] 기존 회계/헬스/리스크 카드 UI/데이터에 영향 없음

**참고 파일**
- `packages/ops-console/src/pages/os/OsDashboard.tsx`

---

## 2. App (A-08) 티켓

### [R8S1-A08-1] CS HUD 스켈레톤 추가

**설명**

기존 Accounting HUD 옆에 CS용 HUD 탭/스크린 스켈레톤 추가

현재는 정적/더미 UI만 제공 (네트워크 호출 없음)

**할 일**

- app-expo 내 HUD 네비게이션에 CS용 Stack/탭 추가 (예: "회계 / CS" 탭)
- `CSHUDScreen` 컴포넌트 생성
- 상단: "CS HUD (스켈레톤)" 헤더
- 본문: "R8에서 고객지원 티켓 요약/추천 UI 제공 예정" 문구, placeholder 카드 1~2개

**Acceptance Criteria**

- [ ] `demo:app:mock`, `demo:app:live` 모두에서 CS 탭이 보이고 진입 가능
- [ ] CS HUD 스크린 진입 시 네트워크 요청 0 (Mock/Live 모두)
- [ ] 기존 Accounting HUD 동작에 영향 없음

**참고 파일**
- `packages/app-expo/src/ui/hud/CSHUD.tsx` (신규)
- `packages/app-expo/App.tsx` (탭 네비게이션 추가)

---

### [R8S1-A08-2] SuggestEngine 계층 정리 + LocalLLMEngineV1 Stub 추가

**설명**

기존 SuggestEngine을 범용 인터페이스로 정리

LocalLLMEngineV1 Stub 구현 (실제 모델 호출 없이 더미 응답)

도메인에 독립적인 인터페이스 설계

**할 일**

- SuggestEngine 타입/인터페이스 정의 업데이트

예시:
```typescript
export interface LLMContext {
  domain: 'accounting' | 'cs';
  input: string;
  meta?: Record<string, unknown>;
}

export interface LLMResponse<TPayload = unknown> {
  items: TPayload[];
  engine: 'local' | 'remote';
  debugInfo?: Record<string, unknown>;
}

export interface SuggestEngine {
  suggest<T = unknown>(ctx: LLMContext): Promise<LLMResponse<T>>;
  runMode: 'local-only' | 'remote-only' | 'hybrid';
}
```

- LocalLLMEngineV1 Stub 구현
  - 외부 네트워크 호출 절대 금지
  - 입력 텍스트 일부를 변형한 더미 응답 반환
- `getSuggestEngine()`에서 LocalLLMEngineV1을 선택적으로 사용하도록 플래그만 연결
  (예: `EXPO_PUBLIC_SUGGEST_ENGINE=local`)

**Acceptance Criteria**

- [ ] 기존 회계 Suggest 플로우가 인터페이스 변경 이후에도 정상 동작
- [ ] LocalLLMEngineV1는 테스트에서 직접 호출 가능, 응답 구조 고정
- [ ] 코드 상 어떠한 외부 HTTP/WS 호출도 포함하지 않음
- [ ] CS HUD에서는 추후 이 엔진을 사용할 수 있는 진입점만 존재 (아직 실제 호출은 안 해도 됨)

**참고 파일**
- `packages/app-expo/src/hud/engines/types.ts` (신규)
- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts` (신규)
- `packages/app-expo/src/hud/suggestEngineLocal.ts` (리팩터링)

---

### [R8S1-A08-3] Mock/Live HUD E2E 테스트 확장 (CS 포함)

**설명**

Playwright/E2E 테스트에 CS HUD 기본 시나리오 추가

Mock 모드 네트워크 0 규칙이 CS HUD에도 적용되는지 검증

**할 일**

- `tests/e2e`에 CS HUD 관련 시나리오 추가:
  - Mock 모드: 앱 실행 → CS 탭 진입 → 사용자 액션 1~2개 → Network 요청이 0인지 확인
  - Live 모드: CS 탭 진입 → BFF 설정 오류 시 에러 배너 표출 여부 확인 (기존 패턴 재사용)

**Acceptance Criteria**

- [ ] CI 상 Mock/Live HUD 테스트 모두 통과
- [ ] CS HUD 관련 테스트가 `@smoke` 또는 유사 태그로 지정되어 최소 1회는 항상 실행
- [ ] 회계 HUD 기존 테스트는 그대로 유지/통과

**참고 파일**
- `tests/e2e/mock_mode_network.spec.ts` (신규 또는 확장)

---

## 3. Server (S-07) 티켓

### [R8S1-S07-1] CS 도메인 서비스 코어 패키지 스켈레톤 생성

**설명**

CS 도메인용 service-core 패키지/네임스페이스 골격만 만든다.

실제 DB/업무 로직 없이, 타입/인터페이스/Stub 서비스만 정의.

**할 일**

- `packages/service-core-cs` 또는 유사한 패키지 디렉터리 생성
- 최소 구조:
  - `index.ts` – public interface export
  - `osDashboard.ts` – `/v1/cs/os/dashboard`용 서비스 Stub 함수

예:
```typescript
export async function getCsOsDashboardSummary(tenant: string) {
  return {
    tenant,
    tickets_total: 0,
    tickets_open: 0,
    demo: true,
  };
}
```

- `package.json`/`tsconfig` export 설정

**Acceptance Criteria**

- [ ] `npm run build:packages` 성공
- [ ] 서비스 코어 CS 패키지가 다른 도메인(`service-core-accounting`)을 import 하지 않음
- [ ] 함수/타입 수준에서 "OS Dashboard용 요약 Stub" 정도만 존재 (업무 로직 없음)

**참고 파일**
- `packages/service-core-cs/package.json` (신규)
- `packages/service-core-cs/tsconfig.json` (신규)
- `packages/service-core-cs/src/index.ts` (신규)

---

### [R8S1-S07-2] BFF CS 라우트 스켈레톤 (/v1/cs/os/dashboard)

**설명**

BFF에 CS용 OS Dashboard 라우트 골격 추가

service-core-cs의 Stub을 호출해 그대로 반환

**할 일**

- `bff-accounting/src/routes/cs-os-dashboard.ts` (예시) 추가
- `GET /v1/cs/os/dashboard`
- `requireTenantAuth` + OS 정책 헤더 가드 적용
- `service-core-cs`의 `getCsOsDashboardSummary()` 호출
- `index.ts`에서 라우트 등록

**Acceptance Criteria**

- [ ] BFF 서버 빌드 및 기동 성공
- [ ] `curl`로 `GET /v1/cs/os/dashboard` 호출 시 Stub JSON 응답 확인
- [ ] Multi-tenant 헤더 누락 시 기존 정책대로 401/403 처리
- [ ] 회계 관련 라우트 동작에 영향 없음

**참고 파일**
- `packages/bff-accounting/src/routes/csOsDashboard.ts` (신규)
- `packages/bff-accounting/src/index.ts` (라우트 등록)

---

## 4. Test (T-01) 티켓

### [R8S1-T01-1] Mock 모드 네트워크 0 테스트 (CS HUD 포함)

**설명**

기존 "Mock 모드에서 HTTP 0건" 테스트를 CS HUD까지 확장

**할 일**

- E2E 테스트에서:
  - `demo:app:mock` 기동 후
  - Accounting HUD → CS HUD 순서로 이동
  - 전체 세션 동안 HTTP 요청 수 측정 (Network mock or 프록시 활용)

**Acceptance Criteria**

- [ ] 테스트 이름/설명에 "CS HUD도 포함" 명시
- [ ] 테스트 실패 시 원인(어느 화면에서 HTTP 발생했는지)이 로그에 드러나도록 출력
- [ ] CI 파이프라인에 포함

**참고 파일**
- `tests/e2e/mock_mode_network.spec.ts` (신규 또는 확장)

---

### [R8S1-T01-2] OS Dashboard API 가드 테스트 (CS 확장 후 회귀 방지)

**설명**

`/v1/accounting/os/dashboard` 및 `/v1/cs/os/dashboard`의 파라미터/에러 처리 검증

CS 카드 슬롯 추가 후 기존 응답 스키마가 깨지지 않는지 확인

**할 일**

- 유닛/통합 테스트 추가:
  - `from/to/tenant` 미지정 시 기본값(지난 7일, default tenant) 처리 확인
  - 너무 넓은 기간 요청 시 서버가 적절히 방어(상한)하는지 확인
  - `/v1/cs/os/dashboard` Stub 응답 구조 확인
  - Web Dashboard에서 회계 카드 렌더링에 사용되는 필드가 여전히 존재하는지 확인하는 스냅샷/계약 테스트

**Acceptance Criteria**

- [ ] 두 API 모두 잘못된 파라미터에 대해 4xx/표준 에러 JSON 반환
- [ ] 회계용 OS Dashboard 프런트가 테스트 시 깨지지 않음
- [ ] CS 확장으로 인한 기존 회계/OS 스키마 회귀 없음

**참고 파일**
- `tests/e2e/os_dashboard_guard.spec.ts` (신규)

---

## 5. Definition of Done (R8-S1 전체)

스프린트 종료 시 아래 조건 모두 만족해야 합니다:

### ✅ 회계/기존 OS/HUD 코어의 스키마·지표·라우트 구조 변경 없음

### ✅ CS 도메인은
- [ ] **Web**: 메뉴/라우트 + OS Dashboard 카드 슬롯 + Skeleton UI
- [ ] **App**: HUD 탭 + Skeleton 화면
- [ ] **Server**: `service-core-cs` 패키지 + `/v1/cs/os/dashboard` Stub 라우트
  - 까지만 구현 (실제 티켓/업무/정산 로직 없음)

### ✅ LocalLLMEngineV1는
- [ ] 인터페이스/Stub/플래그까지만 구현
- [ ] 외부 LLM/벤더/모델 호출 없음

### ✅ 테스트
- [ ] Mock 모드 네트워크 0 테스트 + OS Dashboard API 가드 테스트가 CI에서 통과

### ✅ 문서화
- [ ] `docs/R8S1_SPRINT_BRIEF.md`, `R8S1_DETAILED_TASKS.md`에 완료된 부분 반영 및 체크리스트 업데이트

---

## 티켓 우선순위 추천

### P0 (Must Have)
1. [R8S1-00] 브랜치 생성 및 공통 세팅
2. [R8S1-S07-1] CS 도메인 서비스 코어 패키지 스켈레톤
3. [R8S1-S07-2] BFF CS 라우트 스켈레톤
4. [R8S1-W08-1] Web 메뉴/라우트에 CS 섹션 추가
5. [R8S1-A08-1] CS HUD 스켈레톤 추가

### P1 (Should Have)
6. [R8S1-A08-2] SuggestEngine 계층 정리 + LocalLLMEngineV1 Stub
7. [R8S1-W08-2] OS Dashboard에 CS 카드 슬롯 추가
8. [R8S1-T01-1] Mock 모드 네트워크 0 테스트 (CS HUD 포함)

### P2 (Nice to Have)
9. [R8S1-A08-3] Mock/Live HUD E2E 테스트 확장
10. [R8S1-T01-2] OS Dashboard API 가드 테스트

---

## 작업 의존성

```
[R8S1-00] 브랜치 생성
    ↓
[R8S1-S07-1] CS 서비스 코어 패키지
    ↓
[R8S1-S07-2] BFF CS 라우트
    ↓
[R8S1-W08-1] Web CS 섹션 ──┐
    ↓                        │
[R8S1-W08-2] OS Dashboard CS 카드
    ↓
[R8S1-A08-1] CS HUD 스켈레톤 ──┐
    ↓                          │
[R8S1-A08-2] SuggestEngine 정리
    ↓
[R8S1-A08-3] E2E 테스트 ──┐
    ↓                      │
[R8S1-T01-1] Mock 네트워크 0 테스트
    ↓
[R8S1-T01-2] API 가드 테스트
```

---

## 스프린트 보드 설정 예시

### 컬럼
- 📋 Backlog
- 🔄 In Progress
- 👀 Review
- ✅ Done

### 레이블
- `domain:accounting` - 회계 도메인 관련
- `domain:cs` - CS 도메인 관련
- `type:web` - Web 작업
- `type:app` - App 작업
- `type:server` - Server 작업
- `type:test` - Test 작업
- `priority:p0` - Must Have
- `priority:p1` - Should Have
- `priority:p2` - Nice to Have

---

## 참고 문서

- [R8-S1 스프린트 브리핑](./R8S1_SPRINT_BRIEF.md)
- [R8-S1 상세 작업 가이드](./R8S1_DETAILED_TASKS.md)
- [R7-H+4 개발 브리핑](./R7H_PLUS4_DEV_BRIEF.md)

