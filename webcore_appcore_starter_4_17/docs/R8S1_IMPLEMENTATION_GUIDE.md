# R8-S1 스프린트 구현 가이드

---

## 검토팀 승인 메모 (R8-S1 구현 가이드)

본 구현 가이드는 `docs/R8S1_SPRINT_BRIEF.md`, `docs/R8S1_DETAILED_TASKS.md`,  
`docs/R8S1_TICKETS.md` 및 **AI 온디바이스 기업용 플랫폼 – 개발 방향 고정 지시서**를 전제로 한다.

- R8-S1에서는 **회계 / 기존 OS Dashboard / HUD 코어의 스키마·지표·라우트 구조를 변경하지 않는다.**  
  (변경이 필요할 경우 별도 스프린트 또는 RFC로 분리한다.)

- CS 도메인은 이번 스프린트에서  
  **"메뉴/라우트/OS 카드 슬롯 + HUD 스켈레톤 + Stub/BFF 스켈레톤"**까지만 구현한다.

- `LocalLLMEngineV1`는 **인터페이스 / 플래그 / Stub**까지만 구현하며,
  실제 LLM/외부 벤더 연동 코드는 작성하지 않는다.

- Mock 모드에서 **네트워크 요청 0건** 원칙을 유지하며,
  새로 추가되는 CS HUD/라우트 역시 이 원칙을 지킨다.

이 조건을 전제로, 본 구현 가이드를 기준으로 R8-S1 스프린트 구현을 Proceed(집행)한다.

– 검토팀

---

이 문서는 R8-S1 스프린트를 실제로 구현할 때 Cursor에서 바로 사용할 수 있는 프롬프트와 단계별 가이드를 제공합니다.

---

## 0. 공통 – 바로 브랜치 자르고 기준선 맞추기 ([R8S1-00])

### 0-1. 터미널에서 실행

```bash
# 1) 레포 루트로 이동
cd /path/to/webcore_appcore_starter_4_17

# 2) 최신 main 받아오기
git checkout main
git pull origin main

# 3) R8-S1 전용 브랜치 생성
git switch -c r8-s1-cs-skeleton

# 4) 브랜치 원격 등록
git push -u origin r8-s1-cs-skeleton
```

### 0-2. R8-S1 스코프 선언(DoD 세 줄 고정)

**파일**: `docs/R8S1_SPRINT_BRIEF.md` 맨 위에 아래 블록 추가

```markdown
> **R8-S1 스코프 고정(개발팀용)**
> - 회계 / 기존 OS / HUD 코어의 스키마·지표·라우트 구조는 변경하지 않는다.
> - CS 도메인은 R8-S1에서는 "메뉴/라우트/OS 카드 슬롯 + HUD 스켈레톤 + Stub/BFF 스켈레톤"까지만 구현한다.
> - LocalLLMEngineV1는 인터페이스/플래그/Stub까지만 구현하고, 실제 LLM/벤더 연동은 포함하지 않는다.
```

**커밋**:
```bash
git add docs/R8S1_SPRINT_BRIEF.md
git commit -m "chore(r8-s1): lock sprint scope and branch setup"
```

---

## 1. Web – CS 메뉴/라우트 + OS Dashboard 슬롯 ([R8S1-W08-1], [R8S1-W08-2])

### 1-1. CS 섹션 메뉴/라우트 추가 ([R8S1-W08-1])

**목표**: 왼쪽 메뉴에 CS 섹션 추가, `/cs` 라우트 추가, 스켈레톤 화면

#### Cursor 프롬프트

메뉴/라우트 정의가 있는 파일(`packages/ops-console/src/App.tsx`)을 Cursor에서 열고, 아래 텍스트를 Cursor Chat에 그대로 붙여넣고 실행:

```
[R8S1-W08-1] CS 섹션 메뉴/라우트 추가

1. 기존 Accounting / OS Dashboard 메뉴 구조를 그대로 유지한다.
2. 왼쪽 메뉴에 "CS" 섹션을 추가하고, 기본 항목으로 "CS Overview" 하나만 둔다.
3. 경로는 다음과 같이 만든다.
   - path: "/cs" (또는 기존 규칙에 맞춰 "/os/cs" 사용)
   - 컴포넌트 이름은 "CsOverviewPage" 정도로 정의한다.
4. 라우트로 이동했을 때 화면에는 다음 문구만 보여준다.
   - 제목: "CS Overview (R8-S1 Skeleton)"
   - 본문: "CS 도메인 HUD/OS 통합을 위한 스켈레톤 화면입니다."
5. 기존 회계/OS 관련 메뉴/라우트(path, name)는 절대 변경하지 않는다.
6. TypeScript 에러가 없도록 타입까지 정리한다.
```

#### 간단한 JSX 스켈레톤 예시

**파일**: `packages/ops-console/src/pages/cs/CsOverviewPage.tsx` (신규)

```tsx
export function CsOverviewPage() {
  return (
    <div style={{ padding: 24 }}>
      <h1>CS Overview (R8-S1 Skeleton)</h1>
      <p>CS 도메인 HUD/OS 통합을 위한 스켈레톤 화면입니다.</p>
    </div>
  );
}
```

---

### 1-2. OS Dashboard에 CS 카드 슬롯 추가 ([R8S1-W08-2])

**목표**: `/os/dashboard`에 CS용 카드 자리만 추가, 값은 N/A 또는 `--`로 표시

#### Cursor 프롬프트

OS Dashboard 컴포넌트 파일(`packages/ops-console/src/pages/os/OsDashboard.tsx`)에서 실행:

```
[R8S1-W08-2] OS Dashboard에 CS 카드 슬롯 추가

1. OS Dashboard 컴포넌트에서 기존 회계 카드(Top-1 정확도, Manual Review 비율, Risk 등)는 그대로 유지한다.
2. "CS"라는 섹션 또는 카드 그룹을 하나 추가한다.
3. 첫 번째 카드만 정의한다:
   - 제목: "CS 티켓 자동화 (준비 중)"
   - 본문 값: "N/A"
   - 설명/툴팁: "R8-S1에서는 CS 관련 지표 슬롯만 예약합니다. 실제 데이터 연동은 이후 스프린트에서 구현합니다."
4. Dashboard API 응답(JSON) 스키마는 변경하지 않는다.
   - CS 카드 값은 프론트에서 하드코딩된 placeholder로 처리한다.
5. 반응형 레이아웃을 깨지지 않게 카드 컬럼/그리드에 자연스럽게 배치한다.
```

---

## 2. App – CS HUD 스켈레톤 + SuggestEngine / LocalLLMEngineV1 ([A-08 계열])

### 2-1. CS HUD 스켈레톤 ([R8S1-A08-1])

**목표**: HUD 상단 또는 탭에 CS 진입점 추가, Mock 모드에서 네트워크 호출 0

#### Cursor 프롬프트

HUD 루트/탭 컴포넌트(`packages/app-expo/src/ui/AccountingHUD.tsx` 또는 `App.tsx`)에서 실행:

```
[R8S1-A08-1] CS HUD 스켈레톤 추가

1. Accounting HUD와 동일한 패턴으로 CS HUD용 진입점을 추가한다.
   - 예: 상단 탭 "Accounting" 옆에 "CS" 탭 추가
   - 또는 사이드 메뉴에 "CS HUD" 버튼 추가
2. CS HUD 화면 컴포넌트(CSHUD.tsx 정도)를 만든다.
   - 제목: "CS HUD (R8-S1 Skeleton)"
   - 본문: "CS 상담/티켓 업무를 온디바이스로 보조하기 위한 HUD 스켈레톤입니다."
3. Mock 모드에서 이 화면을 띄워도 어떤 네트워크 요청도 발생하지 않도록 한다.
4. Live 모드에서도 아직 BFF 호출은 넣지 않는다.
5. 스타일/컴포넌트는 기존 Accounting HUD와 동일한 Button/Text 패턴을 재사용한다.
```

---

### 2-2. SuggestEngine 계층 정리 + LocalLLMEngineV1 Stub ([R8S1-A08-2])

**목표**: SuggestEngine 인터페이스 확정, LocalLLMEngineV1 Stub 추가

#### 2-2-1. 타입/인터페이스 예시

**파일**: `packages/app-expo/src/hud/engines/types.ts` (신규)

```typescript
export type SuggestDomain = 'accounting' | 'cs';

export interface SuggestContext {
  domain: SuggestDomain;
  tenantId: string;
  userId: string;
  locale?: string;
}

export interface SuggestInput {
  text: string;
  meta?: Record<string, unknown>;
}

export interface SuggestItem<TPayload = unknown> {
  id: string;
  title: string;
  description?: string;
  score?: number;
  payload?: TPayload;
  source: 'local-rule' | 'remote-bff' | 'local-llm';
}

export interface SuggestEngine {
  readonly id: string;
  readonly mode: 'local-only' | 'remote-only' | 'hybrid';

  supportsDomain(domain: SuggestDomain): boolean;

  suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestItem<TPayload>[]>;
}
```

#### 2-2-2. LocalLLMEngineV1 Stub 예시

**파일**: `packages/app-expo/src/hud/engines/localLLMEngineV1.ts` (신규)

```typescript
import type {
  SuggestEngine,
  SuggestContext,
  SuggestInput,
  SuggestItem,
} from './types.js';

export class LocalLLMEngineV1 implements SuggestEngine {
  readonly id = 'local-llm-v1';
  readonly mode = 'local-only' as const;

  supportsDomain(_domain: 'accounting' | 'cs'): boolean {
    return true; // 스켈레톤 단계에서는 모든 도메인 지원으로 둔다.
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestItem<TPayload>[]> {
    // R8-S1에서는 네트워크 호출 없이 간단한 더미 응답만 생성한다.
    const label = ctx.domain === 'accounting' ? '회계' : 'CS';

    return [
      {
        id: 'stub-1',
        title: `[Stub] ${label}용 Local LLM 엔진 자리`,
        description:
          'R8-S1에서는 인터페이스와 흐름만 검증합니다. 실제 LLM은 이후 스프린트에서 붙입니다.',
        score: 0.5,
        payload: undefined as TPayload,
        source: 'local-llm',
      },
    ];
  }
}
```

#### 2-2-3. getSuggestEngine 유틸에 Stub 연결

**파일**: `packages/app-expo/src/hud/engines/index.ts` (신규 또는 수정)

#### Cursor 프롬프트

```
[R8S1-A08-2] getSuggestEngine에 LocalLLMEngineV1 Stub 연결

1. 기존 localRuleEngineV1, remoteEngine 등을 감싸는 getSuggestEngine() 함수를 정의한다.
2. R8-S1에서는 다음 플래그만 고려한다.
   - cfg.suggestMode === 'local-rule' → 기존 로컬 규칙 엔진 사용
   - cfg.suggestMode === 'local-llm' → 새 LocalLLMEngineV1 Stub 사용
   - cfg.suggestMode === 'remote' → 기존 BFF 기반 엔진 사용
3. HUD 상단 상태바에 "Engine: On-device (Rule)", "Engine: On-device (LLM Stub)", "Engine: BFF(remote)" 중 하나가 표시되도록 이어 붙인다.
4. 새 모드 추가로 인한 타입 에러를 모두 정리한다.
5. 어떤 모드에서도 Mock 모드에서는 네트워크 요청이 발생하지 않도록 isMock 체크를 유지한다.
```

---

### 2-3. Mock/Live HUD E2E 테스트 확장 ([R8S1-A08-3])

**목표**: 기존 HUD E2E 시나리오에 CS HUD + 새로운 엔진 모드까지 포함

#### Cursor 프롬프트

테스트 파일(`tests/e2e/` 또는 유사 위치)에서 실행:

```
[R8S1-A08-3] HUD E2E 테스트 확장

1. 기존 Accounting HUD E2E 시나리오를 참고해서,
   - CS HUD 진입 → 안내 문구 표시까지 확인하는 테스트를 추가한다.
2. Mock 모드 기준:
   - CS HUD 탭/메뉴 클릭
   - 화면에 "CS HUD (R8-S1 Skeleton)" 텍스트가 보이는지 검사
3. Live 모드 기준:
   - BFF가 죽어 있더라도, CS HUD 진입 자체는 실패하지 않고
   - 상태바에 BFF 관련 경고가 일관된 형식으로 표출되는지 확인한다.
4. 이 테스트는 R8-S1 브랜치에서 CI에 포함될 수 있도록 tags/describe 블록에 R8S1-A08-3 메타를 남긴다.
```

---

## 3. Server – CS 서비스 코어 + BFF 라우트 스켈레톤 ([S-07 계열])

### 3-1. CS 도메인 서비스 코어 패키지 스켈레톤 ([R8S1-S07-1])

**목표**: `service-core-cs` 패키지 폴더와 최소 엔트리 포인트만 생성

#### 폴더 구조 예

```
packages/
  service-core-accounting/
  service-core-cs/
    package.json
    tsconfig.json
    src/
      index.ts
      osDashboard.ts
```

#### 파일 예시

**파일**: `packages/service-core-cs/src/osDashboard.ts` (신규)

```typescript
export interface CsOsDashboardSummary {
  totalTickets: number | null;
  autoResolvedRate: number | null;
  lastUpdatedAt: string | null;
}

export async function getCsOsDashboardSummary(
  tenantId: string,
): Promise<CsOsDashboardSummary> {
  // R8-S1: Stub 응답
  return {
    totalTickets: null,
    autoResolvedRate: null,
    lastUpdatedAt: null,
  };
}
```

**파일**: `packages/service-core-cs/src/index.ts` (신규)

```typescript
export * from './osDashboard.js';
```

**파일**: `packages/service-core-cs/package.json` (신규)

```json
{
  "name": "@appcore/service-core-cs",
  "version": "0.1.0",
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "type-check": "tsc --noEmit"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

---

### 3-2. BFF CS 라우트 스켈레톤 ([R8S1-S07-2])

**목표**: `/v1/cs/os/dashboard` 라우트 추가, Stub 데이터만 반환

#### Cursor 프롬프트

`packages/bff-accounting/src/routes/` 관련 파일을 열고 아래 프롬프트 실행:

```
[R8S1-S07-2] CS OS Dashboard BFF 라우트 스켈레톤 추가

1. Express Router를 사용해 "/v1/cs/os/dashboard" GET 엔드포인트를 추가한다.
2. OS 정책 브리지 규칙을 따른다.
   - requireTenantAuth, requireRole('operator','auditor') 등 기존 패턴 재사용
3. service-core-cs 패키지의 getCsOsDashboardSummary(tenantId)를 호출한다.
4. 응답 구조는 다음과 같이 둔다.
   {
     "tenant": "<tenant-id>",
     "cs": {
       "os_dashboard": {
         "totalTickets": null,
         "autoResolvedRate": null,
         "lastUpdatedAt": null
       }
     }
   }
5. R8-S1에서는 DB 쿼리를 붙이지 않고, Stub로만 응답한다.
6. 기존 /v1/accounting/os/dashboard 응답 스키마에는 어떤 변경도 가하지 않는다.
```

---

## 4. Test – Mock 네트워크 0 + OS Dashboard 가드 ([T-01 계열])

### 4-1. Mock 모드 네트워크 0 테스트 (CS HUD 포함) ([R8S1-T01-1])

**목표**: `demo:app:mock` 기준으로 E2E에서 HTTP 요청 0건 보장

#### Cursor 프롬프트

테스트 파일(`tests/e2e/mock_mode_network.spec.ts` 또는 유사)에서 실행:

```
[R8S1-T01-1] Mock 모드 네트워크 0 테스트 (CS HUD 포함)

1. demo:app:mock 환경에서 HUD 웹을 띄우는 테스트를 작성한다.
2. 테스트 흐름:
   - 루트 HUD 화면 렌더
   - Accounting HUD 탭에서 한 번 상호작용
   - CS HUD 탭으로 전환 후 "CS HUD (R8-S1 Skeleton)" 텍스트 확인
3. 테스트 실행 동안 발생한 네트워크 요청(HTTP/WS/XHR)이 0건인지 검사한다.
   - Playwright의 page.on('request') 등을 이용해 요청 수를 카운트하고, 최종적으로 0이라고 단언(assert)한다.
4. 이 테스트가 실패하면 CI가 빨갛게 깨지도록 한다.
```

#### 예시 코드 (Playwright)

```typescript
// tests/e2e/mock_mode_network.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Mock Mode Network Zero Test', () => {
  test('should have zero network requests in mock mode (CS HUD included)', async ({ page }) => {
    const requests: string[] = [];
    
    page.on('request', (request) => {
      // HTTP/WS/XHR 요청 모두 카운트
      if (request.url().startsWith('http')) {
        requests.push(request.url());
      }
    });
    
    // HUD 페이지 진입
    await page.goto('http://localhost:8081');
    
    // Accounting HUD 테스트
    await page.click('text=Accounting');
    await page.click('text=추천');
    await page.click('text=승인');
    
    // CS HUD 테스트
    await page.click('text=CS');
    await page.waitForSelector('text=CS HUD (R8-S1 Skeleton)');
    
    // 네트워크 요청 수 검증
    expect(requests.length).toBe(0);
  });
});
```

---

### 4-2. OS Dashboard API 가드 테스트 ([R8S1-T01-2])

**목표**: `/v1/accounting/os/dashboard` + `/v1/cs/os/dashboard` 파라미터 유효성/기본값 테스트

#### Cursor 프롬프트

테스트 파일(`tests/e2e/os_dashboard_guard.spec.ts` 또는 유사)에서 실행:

```
[R8S1-T01-2] OS Dashboard API 가드 테스트

1. 서버 단 API 테스트 또는 통합 테스트에서 다음 케이스를 추가한다.

[accounting/os/dashboard]
- from/to/tenant 없이 호출 시 200 응답 + 기본 지난 7일 범위, 기본 tenant로 처리되는지 확인.
- from/to 기간이 상한을 초과하는 요청은 4xx 또는 명시된 정책대로 처리되는지 확인.
- 잘못된 tenant 값에 대해 4xx 또는 빈 결과가 일관되게 내려오는지 확인.

[cs/os/dashboard]
- 최소한 200 응답 + Stub 구조(JSON 키)가 문서대로 내려오는지 확인.
- accounting/os/dashboard 스키마와 충돌/변경이 없음을 스냅샷 또는 타입 체크로 검증.

2. 테스트 파일 상단/설명에 "R8S1-T01-2" 메타를 주석으로 남겨 추적 가능하게 한다.
```

#### 예시 코드

```typescript
// tests/e2e/os_dashboard_guard.spec.ts
import { test, expect } from '@playwright/test';

/**
 * R8S1-T01-2: OS Dashboard API 가드 테스트
 */
test.describe('OS Dashboard API Guard Tests', () => {
  const baseUrl = 'http://localhost:8081';
  const headers = {
    'X-Tenant': 'default',
    'X-User-Role': 'operator',
    'X-User-Id': 'test-user',
  };

  test('accounting/os/dashboard should default to last 7 days', async ({ request }) => {
    const response = await request.get(`${baseUrl}/v1/accounting/os/dashboard`, {
      headers,
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.window).toBeDefined();
    // 기본값 검증
  });

  test('accounting/os/dashboard should reject invalid date range', async ({ request }) => {
    const response = await request.get(
      `${baseUrl}/v1/accounting/os/dashboard?from=2020-01-01&to=2019-01-01`,
      { headers }
    );
    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.error_code).toBe('INVALID_DATE_RANGE');
  });

  test('cs/os/dashboard should return stub response', async ({ request }) => {
    const response = await request.get(`${baseUrl}/v1/cs/os/dashboard`, {
      headers,
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.cs).toBeDefined();
    expect(data.cs.os_dashboard).toBeDefined();
    expect(data.cs.os_dashboard.totalTickets).toBeNull();
  });
});
```

---

## 5. 마무리 루틴

### 5-1. 작업 중간 체크

위 작업 블록 중 2~3개 끝날 때마다 로컬에서:

```bash
# 타입/빌드 체크
npm run build:packages

# 서버/웹/HUD 스모크
docker compose up -d db bff
npm run db:migrate
npm run demo:web
npm run demo:app:mock
npm run demo:app:live
```

### 5-2. 커밋 루틴

스프린트 중간 중간에는:

```bash
git status
git add <완료된 파일들>
git commit -m "feat(r8-s1): implement <티켓 ID> ..."
git push
```

### 5-3. 커밋 메시지 예시

```bash
# Web 작업
git commit -m "feat(r8-s1): implement W08-1 CS menu/route skeleton"
git commit -m "feat(r8-s1): implement W08-2 OS Dashboard CS card slot"

# App 작업
git commit -m "feat(r8-s1): implement A08-1 CS HUD skeleton"
git commit -m "feat(r8-s1): implement A08-2 SuggestEngine refactor + LocalLLMEngineV1 stub"

# Server 작업
git commit -m "feat(r8-s1): implement S07-1 CS service-core package skeleton"
git commit -m "feat(r8-s1): implement S07-2 BFF CS OS dashboard route"

# Test 작업
git commit -m "test(r8-s1): implement T01-1 mock mode network zero test"
git commit -m "test(r8-s1): implement T01-2 OS Dashboard API guard tests"
```

---

## 6. 작업 순서 추천

### Phase 1: 기반 구조 (Day 1-2)
1. [R8S1-00] 브랜치 생성 및 스코프 고정
2. [R8S1-S07-1] CS 서비스 코어 패키지 스켈레톤
3. [R8S1-S07-2] BFF CS 라우트 스켈레톤

### Phase 2: Web UI (Day 3-4)
4. [R8S1-W08-1] Web 메뉴/라우트에 CS 섹션 추가
5. [R8S1-W08-2] OS Dashboard에 CS 카드 슬롯 추가

### Phase 3: App HUD (Day 5-7)
6. [R8S1-A08-1] CS HUD 스켈레톤 추가
7. [R8S1-A08-2] SuggestEngine 계층 정리 + LocalLLMEngineV1 Stub

### Phase 4: 테스트 (Day 8-10)
8. [R8S1-A08-3] Mock/Live HUD E2E 테스트 확장
9. [R8S1-T01-1] Mock 모드 네트워크 0 테스트
10. [R8S1-T01-2] OS Dashboard API 가드 테스트

---

## 7. 트러블슈팅

### 타입 에러 발생 시
```bash
# 모든 패키지 타입 체크
npm run type-check --workspaces

# 특정 패키지만
npm run type-check --workspace=@appcore/service-core-cs
```

### 빌드 실패 시
```bash
# 클린 빌드
rm -rf node_modules packages/*/node_modules
npm install
npm run build:packages
```

### 테스트 실패 시
```bash
# Mock 모드 네트워크 테스트만 실행
npm test -- tests/e2e/mock_mode_network.spec.ts

# OS Dashboard 가드 테스트만 실행
npm test -- tests/e2e/os_dashboard_guard.spec.ts
```

---

## 8. 완료 체크리스트

스프린트 종료 전 확인:

- [ ] 모든 티켓의 Acceptance Criteria 만족
- [ ] 타입 에러 0개
- [ ] 빌드 성공 (`npm run build:packages`)
- [ ] 모든 테스트 통과
- [ ] Mock 모드에서 네트워크 요청 0건 확인
- [ ] 기존 회계/OS 기능 정상 동작 확인
- [ ] 문서 업데이트 (`R8S1_SPRINT_BRIEF.md`, `R8S1_DETAILED_TASKS.md`)

---

## 참고 문서

- [R8-S1 스프린트 브리핑](./R8S1_SPRINT_BRIEF.md)
- [R8-S1 상세 작업 가이드](./R8S1_DETAILED_TASKS.md)
- [R8-S1 개별 티켓](./R8S1_TICKETS.md)

