# R8-S1 스프린트 상세 작업 가이드

## 0. 브랜치 & 공통 준비

### 브랜치 생성
```bash
git checkout main
git pull origin main
git switch -c r8-s1-cs-skeleton
```

### 기준선
- **기준**: `r7-h-final-20251208` 이후 main
- **원칙**: 회계/OS/HUD 기존 기능에는 구조 변경 금지 (버그 수정 외 X)

---

## 1. Web (W-08) – CS 도메인 스켈레톤 + OS Dashboard 확장

### W-08-1. 메뉴/라우트에 CS 섹션 추가

**목표**: "OS 안에 두 번째 도메인(CS)이 붙었다"는 걸 메뉴 구조만으로 이해 가능하게 만들기.

#### 구체 작업

1. **ops-console 라우팅에 CS 섹션 추가**
   - 예: `/cs/dashboard` (추후용, 지금은 "Coming soon / Stub" 정도)

2. **사이드바 메뉴 구조**:
   ```
   - OS Dashboard
   - Accounting
   - CS (새 섹션)
     - CS Overview (stub)
   ```

3. **네이밍 원칙**:
   - URL: `/cs/...`
   - 메뉴명: "CS Overview" / "CS Dashboard" 수준의 관제/요약 용어 (티켓 시스템 용어 X)

#### 파일 수정
- `packages/ops-console/src/App.tsx` - 메뉴 구조 추가
- `packages/ops-console/src/pages/cs/CSOverview.tsx` (신규) - Stub 페이지

#### 예시 코드
```tsx
// packages/ops-console/src/pages/cs/CSOverview.tsx
export default function CSOverview() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-4">CS Overview</h1>
      <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded">
        <p className="font-semibold">Coming Soon</p>
        <p className="text-sm">CS 도메인 모듈이 준비 중입니다.</p>
      </div>
    </div>
  );
}
```

---

### W-08-2. OS Dashboard에 CS 카드 자리 만들기

**목표**: 아직 데이터는 없어도, "멀티 도메인 OS" 느낌을 전달.

#### 구체 작업

1. **`/os/dashboard` 레이아웃에 CS용 카드 슬롯 1~2개 추가**
   - 예:
     - "CS 티켓 처리 현황 (준비 중)"
     - "CS 응답 SLA (준비 중)"

2. **현재는 Stub 데이터만 노출**:
   - demo 모드에서는 `--` 또는 "준비 중(Coming soon)" 텍스트
   - 실제 `/v1/cs/os/dashboard` 응답 스키마에 맞게 타입만 정의해 두고, 값은 하드코딩 또는 mock

#### DoD
- ✅ 회계 카드 레이아웃/텍스트는 변경 없음
- ✅ CS 카드는 추가만 (삭제/이동 없음)

#### 파일 수정
- `packages/ops-console/src/pages/os/OsDashboard.tsx` - CS 카드 섹션 추가

#### 예시 코드
```tsx
// OS Dashboard 하단에 추가
<div className="bg-white rounded-lg shadow p-6 mt-8">
  <h2 className="text-xl font-semibold mb-4">CS 모듈 (준비 중)</h2>
  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div className="bg-gray-50 p-6 rounded-lg border-l-4 border-gray-400">
      <h3 className="text-sm font-medium text-gray-500 mb-2">
        CS 티켓 처리 현황
      </h3>
      <p className="text-3xl font-bold text-gray-400">--</p>
      <p className="text-xs text-gray-500 mt-2">준비 중</p>
    </div>
    <div className="bg-gray-50 p-6 rounded-lg border-l-4 border-gray-400">
      <h3 className="text-sm font-medium text-gray-500 mb-2">
        CS 응답 SLA
      </h3>
      <p className="text-3xl font-bold text-gray-400">--</p>
      <p className="text-xs text-gray-500 mt-2">준비 중</p>
    </div>
  </div>
</div>
```

---

## 2. App (A-08) – CS HUD 스켈레톤 + 엔진 계층 정리

### A-08-1. CS HUD 스켈레톤 추가

**목표**: HUD 안에 "CS 뷰"가 들어갈 자리를 미리 확보.

#### 구체 작업

1. **app-expo에서 HUD 엔트리 구조 확인** (AccountingHUD와 동일 패턴)

2. **CS용 HUD 컴포넌트 추가**:
   - 예: `src/ui/hud/CSHUD.tsx`
   - 기능: 지금은
     - 상단에 "CS HUD (스켈레톤)" 제목
     - 더미 리스트 1~2개 (예: 문의 제목, 상태)
     - 아래에 "향후 온디바이스 LLM 기반 답변 제안 예정" 텍스트 정도

3. **HUD 안에서 탭/네비게이션으로 전환 가능하게**:
   - 예: "Accounting / CS" 탭 또는 드롭다운

**스프린트 목표는 "틀만 보이게"지, CS 로직 구현이 아닙니다.**

#### 파일 생성
- `packages/app-expo/src/ui/hud/CSHUD.tsx` (신규)

#### 예시 코드
```tsx
// packages/app-expo/src/ui/hud/CSHUD.tsx
import { View, Text, ScrollView } from 'react-native';

export default function CSHUD() {
  return (
    <ScrollView style={{ flex: 1, padding: 16 }}>
      <Text style={{ fontSize: 24, fontWeight: 'bold', marginBottom: 16 }}>
        CS HUD (스켈레톤)
      </Text>
      
      {/* 더미 티켓 리스트 */}
      <View style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 18, fontWeight: '600', marginBottom: 8 }}>
          티켓 목록
        </Text>
        <View style={{ backgroundColor: '#f5f5f5', padding: 12, borderRadius: 8, marginBottom: 8 }}>
          <Text style={{ fontWeight: '600' }}>문의 #1: 결제 오류</Text>
          <Text style={{ color: '#666', fontSize: 12, marginTop: 4 }}>
            상태: 대기 중
          </Text>
        </View>
        <View style={{ backgroundColor: '#f5f5f5', padding: 12, borderRadius: 8 }}>
          <Text style={{ fontWeight: '600' }}>문의 #2: 환불 요청</Text>
          <Text style={{ color: '#666', fontSize: 12, marginTop: 4 }}>
            상태: 처리 중
          </Text>
        </View>
      </View>
      
      <View style={{ backgroundColor: '#e3f2fd', padding: 12, borderRadius: 8 }}>
        <Text style={{ fontSize: 14, color: '#1976d2' }}>
          향후 온디바이스 LLM 기반 답변 제안 예정
        </Text>
      </View>
    </ScrollView>
  );
}
```

---

### A-08-2. SuggestEngine 계층 정리 + LocalLLMEngineV1 Stub

**목표**: R8 이후 온디바이스 LLM을 꽂을 표준 인터페이스를 먼저 고정.

#### 구체 작업

1. **엔진 타입 정의 파일 추가**:
   - 예: `app-expo/src/hud/engines/types.ts`

```typescript
// packages/app-expo/src/hud/engines/types.ts
export interface SuggestInput {
  domain: 'accounting' | 'cs';
  query: string;
  context?: Record<string, any>;
}

export interface SuggestResult {
  items: Array<{
    id: string;
    title?: string;
    body?: string;
    score?: number;
    [key: string]: any;
  }>;
  engine: string;
  confidence?: number;
}

export interface SuggestEngine {
  id: string;  // 'local-rule-v1' | 'local-llm-v1' | 'remote-bff-v1' ...
  mode: 'on-device' | 'remote';
  domain: 'accounting' | 'cs';
  suggest(input: SuggestInput): Promise<SuggestResult>;
}
```

2. **LocalRuleEngineV1 → 이 인터페이스 구현으로 리팩터**:
   - 기존 회계용 규칙 엔진을 새 인터페이스에 맞게 연결

3. **LocalLLMEngineV1 Stub 추가**:
   - 같은 위치에 Stub 클래스/함수만 구현

```typescript
// packages/app-expo/src/hud/engines/localLLMEngineV1.ts
import { SuggestEngine, SuggestInput, SuggestResult } from './types.js';

export const LocalLLMEngineV1: SuggestEngine = {
  id: 'local-llm-v1',
  mode: 'on-device',
  domain: 'cs',
  async suggest(input: SuggestInput): Promise<SuggestResult> {
    // TODO: R8-S2에서 실제 온디바이스 LLM 탑재
    return {
      items: [
        {
          id: 'stub-1',
          title: '온디바이스 LLM Stub 응답',
          body: 'R8-S2에서 실제 모델로 대체될 예정입니다.',
          score: 0.5,
        },
      ],
      engine: 'local-llm-v1',
      confidence: 0.5,
    };
  },
};
```

4. **HUD 상단 상태바에 표시**:
   - Accounting HUD: `Engine: LocalRuleEngineV1 / BFF(remote)`
   - CS HUD: `Engine: LocalLLMEngineV1 (stub)` (Mock에서는 로컬, Live에서도 아직 동일 Stub)

#### 파일 생성/수정
- `packages/app-expo/src/hud/engines/types.ts` (신규)
- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts` (신규)
- `packages/app-expo/src/hud/suggestEngineLocal.ts` - 리팩터링
- `packages/app-expo/src/ui/hud/CSHUD.tsx` - 엔진 표시 추가

---

### A-08-3. Mock/Live 테스트 자동화 (CS 버전 포함)

**목표**: R7-H에서 만든 "Mock 네트워크 0" 원칙을 CS까지 확장.

#### 구체 작업

1. **E2E/통합 테스트에 케이스 추가**:
   - `demo:app:mock` 상태에서:
     - Accounting HUD + CS HUD 모두 열어본 뒤
     - fetch/XHR 호출이 0인지 검사

2. **CS HUD 기본 렌더 테스트**:
   - Jest 또는 React Testing Library로
   - "CS HUD (스켈레톤)" 텍스트가 뜨는지만 확인해도 OK

#### 파일 생성
- `tests/e2e/mock_mode_network.spec.ts` (신규)

#### 예시 코드 (Playwright)
```typescript
// tests/e2e/mock_mode_network.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Mock Mode Network Zero Test', () => {
  test('should have zero network requests in mock mode', async ({ page }) => {
    const requests: string[] = [];
    
    page.on('request', (request) => {
      requests.push(request.url());
    });
    
    // HUD 페이지 진입
    await page.goto('http://localhost:8081');
    
    // Accounting HUD 테스트
    await page.click('text=Accounting');
    await page.click('text=추천');
    await page.click('text=승인');
    
    // CS HUD 테스트
    await page.click('text=CS');
    await page.waitForSelector('text=CS HUD');
    
    // 네트워크 요청 수 검증
    expect(requests.length).toBe(0);
  });
});
```

---

## 3. Server (S-07) – CS 서비스 코어 스켈레톤

### S-07-1. CS 도메인 패키지/네임스페이스 뼈대

**목표**: 회계와 분리된 "CS 서비스 코어"의 뼈대만 만든다.

#### 구체 작업

1. **`packages/service-core-cs` (또는 유사 네이밍) 새 패키지 생성**
   - `package.json`, `tsconfig.json`, `src/index.ts` 등 최소 골격

2. **`src/index.ts`에는**:
```typescript
// packages/service-core-cs/src/index.ts
export interface CsOsDashboardSummary {
  ticket_count: number;
  pending_count: number;
  demo: boolean;
}

export async function getCsOsDashboardSummary(
  tenant: string
): Promise<CsOsDashboardSummary> {
  // TODO: R8-S2에서 실제 데이터 연동
  return {
    ticket_count: 0,
    pending_count: 0,
    demo: true,
  };
}
```

#### 파일 생성
- `packages/service-core-cs/package.json` (신규)
- `packages/service-core-cs/tsconfig.json` (신규)
- `packages/service-core-cs/src/index.ts` (신규)

---

### S-07-2. BFF 라우트 스켈레톤 추가: `/v1/cs/os/dashboard`

**목표**: OS가 CS 도메인을 한 줄 API로 조회할 수 있게 만드는 골격.

#### 구체 작업

1. **`packages/bff-accounting/src/routes/csOsDashboard.ts` 추가**:
```typescript
// packages/bff-accounting/src/routes/csOsDashboard.ts
import { Router } from 'express';
import { requireTenantAuth, requireRole as requireRoleGuard } from '../shared/guards.js';
import { getCsOsDashboardSummary } from '@appcore/service-core-cs';

const router = Router();

router.get(
  '/v1/cs/os/dashboard',
  requireTenantAuth,
  requireRoleGuard('operator', 'auditor'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      const data = await getCsOsDashboardSummary(tenant);
      res.json({ ok: true, data });
    } catch (err) {
      next(err);
    }
  }
);

export default router;
```

2. **`index.ts`에서 이 라우트 등록**:
   - OS Policy Bridge 이후, 다른 `/v1/*` 라우트와 동일한 위치

3. **현재는 `getCsOsDashboardSummary`가 Stub을 반환하므로**
   - DB 마이그레이션/테이블은 이번 스프린트에선 없음

#### 파일 생성/수정
- `packages/bff-accounting/src/routes/csOsDashboard.ts` (신규)
- `packages/bff-accounting/src/index.ts` - 라우트 등록

---

## 4. Test (T-01) – R7-H 회귀 방지 + R8 준비

### T-01-1. Mock 모드 네트워크 0 테스트 (강제)

**목표**: 우리 레포의 "신성한 룰"로 박기.

#### 구체 작업

1. **`tests/e2e/mock_mode_network.spec.ts` (예시) 작성**:
   - `npm run demo:app:mock` 띄운 뒤
   - HUD에서 Accounting / CS 탭 전환
   - 네트워크 요청 수 == 0 검증 (Playwright 기반이면 best)

#### 파일 생성
- `tests/e2e/mock_mode_network.spec.ts` (신규)

---

### T-01-2. OS Dashboard API 가드 테스트

**목표**: R7-H+4에서 추가된 파라미터/기간 가드를 깨지 않도록.

#### 구체 작업

1. **`/v1/accounting/os/dashboard`에 대해**:
   - `from/to` 없이 호출 → 지난 7일 기준 동작
   - 이상하게 긴 기간(`from=5년 전`) → 서버 측 상한 처리/에러 코드 확인
   - `tenant` 누락/이상 값 → 적절한 4xx 반환 확인

2. **같은 패턴을 `/v1/cs/os/dashboard` Stub에도 적용** (기본 200 + stub payload)

#### 파일 생성
- `tests/e2e/os_dashboard_guard.spec.ts` (신규)

#### 예시 코드
```typescript
// tests/e2e/os_dashboard_guard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('OS Dashboard API Guard Tests', () => {
  const baseUrl = 'http://localhost:8081';
  const headers = {
    'X-Tenant': 'default',
    'X-User-Role': 'operator',
    'X-User-Id': 'test-user',
  };

  test('should default to last 7 days when from/to not provided', async ({ request }) => {
    const response = await request.get(`${baseUrl}/v1/accounting/os/dashboard`, {
      headers,
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.window).toBeDefined();
  });

  test('should reject invalid date range', async ({ request }) => {
    const response = await request.get(
      `${baseUrl}/v1/accounting/os/dashboard?from=2020-01-01&to=2019-01-01`,
      { headers }
    );
    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.error_code).toBe('INVALID_DATE_RANGE');
  });

  test('should handle missing tenant gracefully', async ({ request }) => {
    const response = await request.get(`${baseUrl}/v1/accounting/os/dashboard`, {
      headers: {
        'X-User-Role': 'operator',
        'X-User-Id': 'test-user',
      },
    });
    // Should either return 400 or use default tenant
    expect([200, 400, 403]).toContain(response.status());
  });
});
```

---

## 5. Definition of Done (이번 스프린트용)

스프린트 종료 조건을 개발팀 버전으로 다시 쓰면:

### ✅ Accounting / OS / HUD 기존 플로우에 구조적 변경 없음

### ✅ Web
- [ ] 메뉴에 CS 섹션 추가
- [ ] OS Dashboard에 CS 카드 슬롯 노출 (Stub)

### ✅ App
- [ ] CS HUD 스켈레톤 화면 렌더
- [ ] Engine 계층에 LocalLLMEngineV1 Stub 포함
- [ ] Mock 모드에서 Accounting + CS 모두 네트워크 0

### ✅ Server
- [ ] `service-core-cs` 패키지 스켈레톤
- [ ] `/v1/cs/os/dashboard` Stub 라우트 응답

### ✅ Test
- [ ] Mock 모드 네트워크 0 E2E 테스트 추가
- [ ] OS Dashboard API 파라미터 가드 테스트 통과

---

## 작업 순서 추천

1. **브랜치 생성** (0단계)
2. **Server 스켈레톤** (S-07) - 가장 독립적
3. **Web 스켈레톤** (W-08) - Server API 사용
4. **App 스켈레톤** (A-08) - Web과 독립적
5. **테스트** (T-01) - 모든 기능 완성 후

---

## 요약

지금부터 우리는
- 회계/OS/HUD 코어는 건드리지 않고,
- "CS라는 두 번째 도메인"을 플러그인처럼 꽂을 수 있는 구조를 만드는 스프린트를 시작합니다.

이 답변을 기준으로,
이제 개별 티켓(Jira/Linear/노션 Task)로 잘게 쪼개서 스프린트 보드에 올리면 됩니다.

