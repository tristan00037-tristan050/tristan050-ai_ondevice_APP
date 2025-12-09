# R9-S1 스프린트 상세 작업 가이드

## 0. 브랜치 & 공통 준비

### 브랜치 생성
```bash
git checkout main
git pull origin main
git tag r8-s2-done-20251209  # R8-S2 태그 확인
git switch -c r9-s1-cs-v1
```

### 기준선
- **기준**: `r8-s2-done-20251209` 이후 main
- **원칙**: 회계/OS/HUD 기존 기능에는 구조 변경 금지 (버그 수정 외 X)

### 스코프 고정 문장

**R9-S1의 메인 목표는 "CS 도메인 v1 기능"과 "엔진 계층의 멀티 도메인 재사용 검증"이다.**

**제약사항:**
1. 회계/기존 OS/HUD 코어 스키마/지표/라우트는 구조 변경 금지
2. CS 도메인은 R9-S1에서 "작동하는 최소 기능 1개 + OS Dashboard 슬롯 1개"까지만 구현
3. LocalLLMEngineV1는 현 구조를 유지하고, 실제 모델 파일 연동은 R9-S2 이후로 미룬다
4. Mock 모드에서 네트워크 요청 0건 유지 (회귀 테스트 필수)

---

## 1. Web (W-10) – CS OS Dashboard 실제 데이터 표시

### W-10-1. CS OS Dashboard 지표 1개 구현

**목표**: OS Dashboard의 CS 카드에 실제 데이터 1개를 표시하여 "CS 도메인이 동작한다"는 것을 증명

#### 구체 작업

1. **CS OS Dashboard API 응답 구조 정의**
   - `/v1/cs/os/dashboard` 응답 스키마 정의
   - 최소 지표 1개: 예) `daily_new_tickets` (일별 신규 티켓 수)
   - 타입 정의: `packages/ops-console/src/types/cs.ts` (신규)

2. **OS Dashboard CS 카드에 실제 데이터 연동**
   - 기존 Stub 카드를 실제 API 호출로 변경
   - `packages/ops-console/src/pages/os/OsDashboard.tsx` 수정
   - CS 카드에 `daily_new_tickets` 표시

3. **에러 처리**
   - CS API 호출 실패 시 "데이터 없음" 또는 "준비 중" 표시
   - Demo 모드에서는 적절한 안내 문구 표시

#### 파일 수정
- `packages/ops-console/src/pages/os/OsDashboard.tsx` - CS 카드 실제 데이터 연동
- `packages/ops-console/src/types/cs.ts` (신규) - CS 타입 정의
- `packages/ops-console/src/api/cs.ts` (신규) - CS API 클라이언트

#### 예시 코드
```tsx
// packages/ops-console/src/types/cs.ts
export interface CsOsDashboardResponse {
  daily_new_tickets: number;
  // 추후 확장: weekly_resolved, avg_response_time 등
}

// packages/ops-console/src/pages/os/OsDashboard.tsx
async function fetchCsDashboard(): Promise<CsOsDashboardResponse | null> {
  try {
    const res = await fetch('/api/v1/cs/os/dashboard', {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'operator',
        'X-User-Role': 'operator',
      },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// CS 카드 렌더링
function renderCsCard(csData: CsOsDashboardResponse | null) {
  return (
    <SummaryCard title="CS 일별 신규 티켓" tooltip="최근 24시간 기준 신규 티켓 수입니다.">
      <p className="text-3xl font-bold">
        {csData?.daily_new_tickets ?? '--'}
      </p>
      {!csData && (
        <p className="text-xs text-gray-500 mt-2">데이터 준비 중</p>
      )}
    </SummaryCard>
  );
}
```

#### Acceptance Criteria
- [ ] OS Dashboard에서 CS 카드가 실제 API를 호출함
- [ ] `daily_new_tickets` 값이 정상적으로 표시됨
- [ ] API 호출 실패 시 적절한 폴백 UI 표시
- [ ] 회계 카드 레이아웃/기능에 영향 없음

---

### W-10-2. CS 메뉴/라우트 운영용 구조 정리

**목표**: CS 도메인을 위한 최소한의 메뉴/라우트 구조를 정리하여 향후 확장 가능하게 만듦

#### 구체 작업

1. **CS 메뉴 구조 정의**
   - 사이드바에 CS 섹션 추가 (이미 R8-S1에서 Stub으로 존재)
   - CS Overview 페이지를 실제 동작하는 페이지로 업그레이드
   - 최소 기능: "최근 티켓 목록" 또는 "CS 요약" 표시

2. **라우트 구조 정리**
   - `/cs` → CS Overview (메인)
   - `/cs/tickets` (선택, 향후 확장용)
   - 라우트 가드: operator 권한 필요

3. **네비게이션 개선**
   - OS Dashboard CS 카드 클릭 시 `/cs`로 이동
   - CS Overview에서 OS Dashboard로 돌아가기 링크

#### 파일 수정
- `packages/ops-console/src/pages/cs/CSOverview.tsx` - 실제 데이터 표시로 업그레이드
- `packages/ops-console/src/App.tsx` - CS 라우트 구조 정리

#### 예시 코드
```tsx
// packages/ops-console/src/pages/cs/CSOverview.tsx
export default function CSOverview() {
  const [tickets, setTickets] = useState<CsTicket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCsTickets().then(data => {
      setTickets(data || []);
      setLoading(false);
    });
  }, []);

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-4">CS Overview</h1>
      {loading ? (
        <p>로딩 중...</p>
      ) : (
        <div>
          <h2 className="text-lg font-semibold mb-2">최근 티켓</h2>
          {tickets.length === 0 ? (
            <p className="text-gray-500">티켓이 없습니다.</p>
          ) : (
            <ul>
              {tickets.map(ticket => (
                <li key={ticket.id}>{ticket.title}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

#### Acceptance Criteria
- [ ] `/cs` 경로로 접근 시 실제 데이터가 표시됨
- [ ] CS 메뉴가 사이드바에 표시되고 정상 동작함
- [ ] OS Dashboard CS 카드 클릭 시 `/cs`로 이동
- [ ] 회계 관련 메뉴/라우트에 영향 없음

---

## 2. App (A-10) – CsHUD 티켓 리스트 + 엔진 계층 재사용

### A-10-1. CsHUD 티켓 리스트 + 요약 실제 API 연동

**목표**: CsHUD에서 더미 데이터 대신 실제 BFF API를 호출하여 티켓 리스트와 요약을 표시

#### 구체 작업

1. **CS API 클라이언트 구현**
   - `packages/app-expo/src/hud/cs-api.ts` (신규 또는 확장)
   - `getCsTickets()`: 최근 티켓 목록 조회
   - `getCsSummary(ticketId)`: 티켓 요약 조회

2. **CsHUD UI 업그레이드**
   - 티켓 리스트 컴포넌트 구현
   - 티켓 선택 시 요약 표시
   - 로딩 상태 및 에러 처리

3. **Mock/Live 모드 분기**
   - Mock 모드: 더미 데이터 사용, 네트워크 호출 없음
   - Live 모드: 실제 BFF API 호출

#### 파일 수정
- `packages/app-expo/src/ui/CsHUD.tsx` - 실제 API 연동
- `packages/app-expo/src/hud/cs-api.ts` (신규) - CS API 클라이언트

#### 예시 코드
```tsx
// packages/app-expo/src/hud/cs-api.ts
export interface CsTicket {
  id: string;
  title: string;
  status: 'open' | 'in_progress' | 'resolved';
  created_at: string;
}

export interface CsSummary {
  ticket_id: string;
  summary: string;
  key_points: string[];
}

export async function getCsTickets(cfg: ClientCfg): Promise<CsTicket[]> {
  if (cfg.demoMode === 'mock') {
    // Mock 모드: 더미 데이터 반환
    return [
      { id: '1', title: 'Mock Ticket 1', status: 'open', created_at: new Date().toISOString() },
    ];
  }

  const res = await fetch(`${cfg.bffUrl}/v1/cs/tickets`, {
    headers: {
      'X-Tenant': cfg.tenantId || 'default',
      'X-Api-Key': cfg.apiKey || '',
    },
  });
  if (!res.ok) throw new Error('Failed to fetch tickets');
  return await res.json();
}

// packages/app-expo/src/ui/CsHUD.tsx
const [tickets, setTickets] = useState<CsTicket[]>([]);
const [selectedTicket, setSelectedTicket] = useState<CsTicket | null>(null);
const [summary, setSummary] = useState<CsSummary | null>(null);

useEffect(() => {
  getCsTickets(cfg).then(setTickets).catch(console.error);
}, []);

const handleTicketSelect = async (ticket: CsTicket) => {
  setSelectedTicket(ticket);
  const s = await getCsSummary(cfg, ticket.id);
  setSummary(s);
};
```

#### Acceptance Criteria
- [ ] CsHUD에서 최근 티켓 리스트가 표시됨
- [ ] 티켓 선택 시 요약이 표시됨
- [ ] Mock 모드에서 네트워크 호출이 0건 (E2E 테스트로 검증)
- [ ] Live 모드에서 실제 BFF API 호출

---

### A-10-2. CS HUD에서 EngineMode/LocalLLMEngineV1 재사용

**목표**: 회계 도메인에서 만든 SuggestEngine 계층을 CS 도메인에서도 재사용하여 "도메인 공통 엔진"임을 증명

#### 구체 작업

1. **CS SuggestEngine 인터페이스 정의**
   - CS 도메인용 `SuggestRequest` / `SuggestResponse` 타입
   - CS 컨텍스트: 티켓 내용, 카테고리 등

2. **CS SuggestEngine 구현**
   - `packages/app-expo/src/hud/engines/cs-suggest.ts` (신규)
   - `LocalRuleEngineV1Adapter`를 CS 도메인에 맞게 확장
   - 또는 새로운 `CsRuleEngineV1` 구현

3. **CsHUD에 엔진 통합**
   - `getSuggestEngine()`을 CS 도메인에서도 사용
   - 엔진 모드에 따라 다른 추론 경로 사용
   - 상태바에 엔진 모드 표시 (AccountingHUD와 동일)

4. **엔진 모드 전환 테스트**
   - `EXPO_PUBLIC_ENGINE_MODE=local-llm`일 때 CS에서도 LLM 엔진 사용
   - Mock 모드에서는 항상 규칙 엔진 사용

#### 파일 수정
- `packages/app-expo/src/hud/engines/types.ts` - CS 도메인 타입 추가
- `packages/app-expo/src/hud/engines/cs-suggest.ts` (신규) - CS SuggestEngine
- `packages/app-expo/src/hud/engines/index.ts` - CS 엔진 선택 로직
- `packages/app-expo/src/ui/CsHUD.tsx` - 엔진 통합 및 상태바 표시

#### 예시 코드
```tsx
// packages/app-expo/src/hud/engines/types.ts
export interface CsSuggestRequest {
  ticket_content: string;
  category?: string;
  context?: Record<string, any>;
}

export interface CsSuggestResponse {
  suggestions: CsSuggestion[];
  explanation?: string;
}

export interface CsSuggestion {
  action: string;
  confidence: number;
  reasoning?: string;
}

// packages/app-expo/src/hud/engines/cs-suggest.ts
export class CsRuleEngineV1 implements SuggestEngine {
  public meta: SuggestEngineMeta = {
    type: 'rule',
    label: 'CS Rule Engine',
  };
  public isReady: boolean = true;

  async suggest(input: { cfg: ClientCfg; request: CsSuggestRequest }): Promise<CsSuggestResponse> {
    // CS 도메인 규칙 기반 추천 로직
    const suggestions: CsSuggestion[] = [];
    // ... 규칙 기반 분류 로직
    return { suggestions };
  }
}

// packages/app-expo/src/ui/CsHUD.tsx
const engine = getSuggestEngine(cfg, 'cs');
const [engineMeta, setEngineMeta] = useState<SuggestEngineMeta | null>(null);

useEffect(() => {
  if (engine.initialize) {
    engine.initialize().then(() => {
      setEngineMeta(engine.meta);
    });
  } else {
    setEngineMeta(engine.meta);
  }
}, []);

// 상태바 표시
<Text>Engine: {engineMeta?.label || 'Loading...'}</Text>
```

#### Acceptance Criteria
- [ ] CS HUD에서 SuggestEngine을 사용하여 추천 생성
- [ ] 엔진 모드에 따라 다른 추론 경로 사용 (rule / local-llm)
- [ ] 상태바에 현재 엔진 모드 표시
- [ ] Mock 모드에서 네트워크 호출 0건 유지
- [ ] 회계 HUD의 엔진 계층과 동일한 인터페이스 사용

---

## 3. Server (S-09) – CS 도메인 로직 및 API 구현

### S-09-1. service-core-cs 도메인 로직 v1 (티켓 목록/요약)

**목표**: service-core-cs 패키지에 실제 CS 도메인 로직을 구현하여 티켓 목록 조회 및 요약 생성 기능 제공

#### 구체 작업

1. **CS 티켓 데이터 모델 정의**
   - `packages/service-core-cs/src/models/ticket.ts` (신규)
   - 티켓 엔티티: id, title, content, status, created_at 등

2. **CS Repository 구현**
   - `packages/service-core-cs/src/repositories/ticket-repository.ts` (신규)
   - `getRecentTickets(tenant, limit)`: 최근 티켓 목록 조회
   - `getTicketById(tenant, ticketId)`: 티켓 상세 조회

3. **CS 요약 로직 구현**
   - `packages/service-core-cs/src/services/summary-service.ts` (신규)
   - 간단한 규칙 기반 요약 생성 (초기 버전)
   - 추후 LLM 기반 요약으로 확장 가능한 구조

4. **CS Audit 이벤트 정의**
   - `cs_ticket_viewed`, `cs_summary_generated` 등
   - Audit 이벤트 타입 및 페이로드 정의

#### 파일 수정
- `packages/service-core-cs/src/models/ticket.ts` (신규)
- `packages/service-core-cs/src/repositories/ticket-repository.ts` (신규)
- `packages/service-core-cs/src/services/summary-service.ts` (신규)
- `packages/service-core-cs/src/index.ts` - Export 추가

#### 예시 코드
```typescript
// packages/service-core-cs/src/models/ticket.ts
export interface CsTicket {
  id: string;
  tenant: string;
  title: string;
  content: string;
  status: 'open' | 'in_progress' | 'resolved';
  category?: string;
  created_at: Date;
  updated_at: Date;
}

// packages/service-core-cs/src/repositories/ticket-repository.ts
export class TicketRepository {
  constructor(private pool: Pool) {}

  async getRecentTickets(tenant: string, limit: number = 10): Promise<CsTicket[]> {
    const result = await this.pool.query(
      `SELECT * FROM cs_tickets 
       WHERE tenant = $1 
       ORDER BY created_at DESC 
       LIMIT $2`,
      [tenant, limit]
    );
    return result.rows.map(this.mapRowToTicket);
  }

  async getTicketById(tenant: string, ticketId: string): Promise<CsTicket | null> {
    const result = await this.pool.query(
      `SELECT * FROM cs_tickets WHERE tenant = $1 AND id = $2`,
      [tenant, ticketId]
    );
    return result.rows.length > 0 ? this.mapRowToTicket(result.rows[0]) : null;
  }
}

// packages/service-core-cs/src/services/summary-service.ts
export class SummaryService {
  async generateSummary(ticket: CsTicket): Promise<string> {
    // 초기 버전: 간단한 규칙 기반 요약
    // 추후 LLM 기반으로 확장 가능
    const keywords = this.extractKeywords(ticket.content);
    return `이 티켓은 ${ticket.category || '일반'} 카테고리로, 
            ${keywords.join(', ')} 관련 내용을 다룹니다.`;
  }
}
```

#### Acceptance Criteria
- [ ] `getRecentTickets()`가 실제 DB에서 티켓 목록을 조회함
- [ ] `generateSummary()`가 티켓 내용을 기반으로 요약을 생성함
- [ ] CS Audit 이벤트가 적절히 기록됨
- [ ] 회계 도메인 코드에 영향 없음

---

### S-09-2. /v1/cs/* BFF 라우트 구현 및 OS 정책 헤더 가드

**목표**: CS 도메인을 위한 BFF API 엔드포인트를 구현하고 OS 정책 가드를 적용

#### 구체 작업

1. **CS BFF 라우트 구현**
   - `packages/bff-accounting/src/routes/cs-tickets.ts` (신규)
   - `GET /v1/cs/tickets`: 최근 티켓 목록
   - `GET /v1/cs/tickets/:id`: 티켓 상세
   - `GET /v1/cs/tickets/:id/summary`: 티켓 요약

2. **CS OS Dashboard 라우트 구현**
   - `packages/bff-accounting/src/routes/cs-os-dashboard.ts` (기존 Stub 업그레이드)
   - `GET /v1/cs/os/dashboard`: CS 집계 데이터
   - `daily_new_tickets` 집계

3. **OS 정책 가드 적용**
   - `requireTenantAuth`, `requireRole('operator')` 적용
   - X-Engine-Mode 헤더 수집 (CS Suggest 호출 시)

4. **BFF 라우트 등록**
   - `packages/bff-accounting/src/index.ts`에서 CS 라우트 등록
   - 기존 회계 라우트와 병렬로 동작

#### 파일 수정
- `packages/bff-accounting/src/routes/cs-tickets.ts` (신규)
- `packages/bff-accounting/src/routes/cs-os-dashboard.ts` - 실제 구현으로 업그레이드
- `packages/bff-accounting/src/index.ts` - CS 라우트 등록

#### 예시 코드
```typescript
// packages/bff-accounting/src/routes/cs-tickets.ts
import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { getCsTickets, getCsTicketSummary } from '@appcore/service-core-cs';

const router = Router();

router.get(
  '/tickets',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || 'default';
      const limit = parseInt(req.query.limit as string) || 10;
      const tickets = await getCsTickets(tenant, limit);
      res.json(tickets);
    } catch (e: any) {
      next(e);
    }
  }
);

router.get(
  '/tickets/:id/summary',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || 'default';
      const ticketId = req.params.id;
      const summary = await getCsTicketSummary(tenant, ticketId);
      res.json({ summary });
    } catch (e: any) {
      next(e);
    }
  }
);

export default router;

// packages/bff-accounting/src/routes/cs-os-dashboard.ts
router.get(
  '/dashboard',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || 'default';
      const from = new Date(Date.now() - 24 * 60 * 60 * 1000);
      
      const result = await pool.query(
        `SELECT COUNT(*) as cnt 
         FROM cs_tickets 
         WHERE tenant = $1 AND created_at >= $2`,
        [tenant, from]
      );
      
      res.json({
        daily_new_tickets: parseInt(result.rows[0].cnt, 10),
      });
    } catch (e: any) {
      next(e);
    }
  }
);
```

#### Acceptance Criteria
- [ ] `/v1/cs/tickets` API가 정상 동작함
- [ ] `/v1/cs/os/dashboard` API가 실제 데이터를 반환함
- [ ] OS 정책 가드가 적용되어 인증 없이 접근 시 403 반환
- [ ] 회계 라우트에 영향 없음

---

### S-09-3. CS 데이터베이스 스키마 및 집계 뷰

**목표**: CS 도메인을 위한 최소한의 DB 스키마를 생성하고 집계 뷰를 추가

#### 구체 작업

1. **CS 티켓 테이블 생성**
   - `packages/data-pg/migrations/011_cs_tickets.sql` (신규)
   - `cs_tickets` 테이블: id, tenant, title, content, status, category, created_at, updated_at

2. **CS Audit 이벤트 테이블 (선택)**
   - 회계와 동일한 `audit_events` 테이블 사용 또는 별도 `cs_audit_events` 테이블
   - `event_type`에 `cs_` 접두사 사용

3. **CS 집계 뷰 생성**
   - `packages/data-pg/migrations/012_cs_os_summary.sql` (신규)
   - `cs_os_summary` 뷰: 일별 신규 티켓 수 집계

#### 파일 수정
- `packages/data-pg/migrations/011_cs_tickets.sql` (신규)
- `packages/data-pg/migrations/012_cs_os_summary.sql` (신규)

#### 예시 코드
```sql
-- packages/data-pg/migrations/011_cs_tickets.sql
CREATE TABLE cs_tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved')),
  category TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cs_tickets_tenant_created ON cs_tickets(tenant, created_at DESC);
CREATE INDEX idx_cs_tickets_status ON cs_tickets(tenant, status);

-- packages/data-pg/migrations/012_cs_os_summary.sql
CREATE VIEW cs_os_summary AS
SELECT
  tenant,
  COUNT(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS daily_new_tickets,
  COUNT(*) FILTER (WHERE status = 'open') AS open_tickets,
  COUNT(*) FILTER (WHERE status = 'resolved' AND updated_at >= now() - interval '24 hours') AS resolved_24h
FROM cs_tickets
GROUP BY tenant;
```

#### Acceptance Criteria
- [ ] `cs_tickets` 테이블이 생성되고 마이그레이션이 적용됨
- [ ] `cs_os_summary` 뷰가 정상 동작함
- [ ] 회계 테이블/뷰에 영향 없음

---

## 4. Test (T-03) – CS 도메인 테스트

### T-03-1. CsHUD Mock/Live E2E 테스트

**목표**: CsHUD가 Mock 모드와 Live 모드에서 올바르게 동작하는지 E2E 테스트로 검증

#### 구체 작업

1. **CsHUD Mock 모드 테스트**
   - `packages/app-expo/e2e/cs-hud-mock.spec.mjs` (신규)
   - 네트워크 요청 0건 검증
   - 더미 데이터 표시 확인

2. **CsHUD Live 모드 테스트**
   - `packages/app-expo/e2e/cs-hud-live.spec.mjs` (신규)
   - 실제 API 호출 확인
   - 티켓 리스트 및 요약 표시 확인

3. **엔진 모드 전환 테스트**
   - `EXPO_PUBLIC_ENGINE_MODE=local-llm`일 때 CS에서도 LLM 엔진 사용 확인
   - Mock 모드에서는 항상 규칙 엔진 사용 확인

#### 파일 수정
- `packages/app-expo/e2e/cs-hud-mock.spec.mjs` (신규)
- `packages/app-expo/e2e/cs-hud-live.spec.mjs` (신규)

#### 예시 코드
```javascript
// packages/app-expo/e2e/cs-hud-mock.spec.mjs
import { test, expect } from '@playwright/test';

test('CS HUD Mock mode should not perform any HTTP requests', async ({ page }) => {
  const requests = [];
  page.on('request', (req) => {
    const url = req.url();
    if (url.startsWith('http') && !url.startsWith('data:') && !url.startsWith('about:')) {
      requests.push(url);
    }
  });

  await page.goto('http://localhost:19006/?mode=mock&domain=cs');
  await page.waitForTimeout(2000);

  expect(requests.length).toBe(0);
});
```

#### Acceptance Criteria
- [ ] Mock 모드에서 네트워크 요청 0건 (회귀 테스트 통과)
- [ ] Live 모드에서 실제 API 호출 및 데이터 표시
- [ ] 엔진 모드 전환 시 올바른 엔진 사용

---

### T-03-2. CS OS Dashboard/API 가드 테스트

**목표**: CS OS Dashboard API의 스키마 및 가드를 검증

#### 구체 작업

1. **CS OS Dashboard API 테스트**
   - `packages/bff-accounting/test/cs-os-dashboard-guards.test.mjs` (신규)
   - 200 OK 및 응답 스키마 검증
   - `daily_new_tickets` 필드 존재 확인

2. **CS Tickets API 가드 테스트**
   - 인증 없이 접근 시 403 Forbidden
   - operator 권한 필요 확인

3. **회귀 테스트**
   - 회계 OS Dashboard API가 여전히 정상 동작하는지 확인

#### 파일 수정
- `packages/bff-accounting/test/cs-os-dashboard-guards.test.mjs` (신규)

#### 예시 코드
```javascript
// packages/bff-accounting/test/cs-os-dashboard-guards.test.mjs
import assert from 'node:assert';

const BFF_URL = process.env.BFF_URL || 'http://localhost:8081';

async function test(name, fn) {
  try {
    await fn();
    console.log(`✅ ${name}`);
  } catch (e) {
    console.error(`❌ ${name}`);
    console.error(`   ${e.message}`);
    throw e;
  }
}

async function main() {
  await test('CS OS Dashboard - 200 OK 및 스키마 검증', async () => {
    const res = await fetch(`${BFF_URL}/v1/cs/os/dashboard`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'test-user',
        'X-User-Role': 'operator',
        'X-Api-Key': 'collector-key:operator',
      },
    });
    assert.strictEqual(res.status, 200);
    const body = await res.json();
    assert(typeof body.daily_new_tickets === 'number');
  });

  await test('CS OS Dashboard - 인증 없이 접근 시 403', async () => {
    const res = await fetch(`${BFF_URL}/v1/cs/os/dashboard`);
    assert.strictEqual(res.status, 403);
  });
}

main().catch(console.error);
```

#### Acceptance Criteria
- [ ] CS OS Dashboard API가 올바른 스키마로 응답
- [ ] 인증 가드가 정상 동작
- [ ] 회계 OS Dashboard API 회귀 테스트 통과

---

## 5. Definition of Done

### 전체 DoD 체크리스트

- [ ] **CS 도메인에서 최소 1개 플로우를 엔드투엔드로 시연 가능**
  - CsHUD에서 티켓 리스트 조회 → 티켓 선택 → 요약 표시
  - OS Dashboard에서 CS 카드에 실제 데이터 표시

- [ ] **회계/기존 OS/HUD 코어 구조 변경 없음**
  - 회계 라우트/API 정상 동작
  - 회계 OS Dashboard 카드 정상 동작
  - AccountingHUD 정상 동작

- [ ] **Mock 모드 네트워크 0 유지**
  - CsHUD Mock 모드 E2E 테스트 통과
  - AccountingHUD Mock 모드 회귀 테스트 통과

- [ ] **엔진 계층의 멀티 도메인 재사용 검증**
  - CS HUD에서 SuggestEngine 사용
  - 엔진 모드 전환 시 CS에서도 올바른 엔진 사용
  - 회계와 CS가 동일한 엔진 인터페이스 사용

- [ ] **모든 테스트 통과**
  - CS E2E 테스트 (Mock/Live)
  - CS API 가드 테스트
  - 회계 회귀 테스트

---

## 참고 파일 경로

### App
- `packages/app-expo/src/ui/CsHUD.tsx`
- `packages/app-expo/src/hud/cs-api.ts` (신규)
- `packages/app-expo/src/hud/engines/cs-suggest.ts` (신규)
- `packages/app-expo/src/hud/engines/types.ts`
- `packages/app-expo/src/hud/engines/index.ts`

### Server
- `packages/service-core-cs/src/models/ticket.ts` (신규)
- `packages/service-core-cs/src/repositories/ticket-repository.ts` (신규)
- `packages/service-core-cs/src/services/summary-service.ts` (신규)
- `packages/bff-accounting/src/routes/cs-tickets.ts` (신규)
- `packages/bff-accounting/src/routes/cs-os-dashboard.ts`
- `packages/bff-accounting/src/index.ts`

### Data
- `packages/data-pg/migrations/011_cs_tickets.sql` (신규)
- `packages/data-pg/migrations/012_cs_os_summary.sql` (신규)

### Web
- `packages/ops-console/src/pages/cs/CSOverview.tsx`
- `packages/ops-console/src/pages/os/OsDashboard.tsx`
- `packages/ops-console/src/types/cs.ts` (신규)
- `packages/ops-console/src/api/cs.ts` (신규)

### Test
- `packages/app-expo/e2e/cs-hud-mock.spec.mjs` (신규)
- `packages/app-expo/e2e/cs-hud-live.spec.mjs` (신규)
- `packages/bff-accounting/test/cs-os-dashboard-guards.test.mjs` (신규)

