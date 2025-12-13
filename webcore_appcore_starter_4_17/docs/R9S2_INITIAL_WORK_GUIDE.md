# R9-S2 초기 작업 가이드

## 목표

R9-S2 스프린트에서 CS 도메인에 LocalLLMEngineV1(SuggestEngine)을 연동합니다.

- 회계 도메인에서 이미 구현된 SuggestEngine / LocalLLMEngineV1 패턴을 최대한 재사용
- `DEMO_MODE=mock`인 경우에는 `ENGINE_MODE` 값과 관계없이 네트워크 요청 0을 유지
- 'remote' 모드는 이번 스프린트에서는 타입/플래그 정의까지만 포함하고, 실제 원격 호출 구현은 포함하지 않음

## 참고 문서

- `docs/R9S2_SPRINT_BRIEF.md`
- `docs/R9S2_TICKETS.md`
- `packages/app-expo/src/hud/engines/*`
- `packages/app-expo/src/ui/CsHUD.tsx`
- `packages/app-expo/src/ui/AccountingHUD.tsx` (참고)

## 우선 작업 티켓

- **[R9S2-A11-1]** CsHUD에 SuggestEngine 통합
- **[R9S2-SC10-1]** CS LLM 서비스 인터페이스 정의

## 변경 파일 목록

### 1. Service-Core-CS

#### 신규 파일: `packages/service-core-cs/src/domain/csLLMService.ts`

CS LLM 서비스를 위한 인터페이스 skeleton을 추가합니다.

**주요 메서드:**
- `getTicketSummaryLLMInput(ticket: CsTicket): CsLLMContext` - 티켓을 LLM 입력 형식으로 변환
- `saveTicketSuggestionStub(suggestion: CsLLMResponse): void` - 추천 결과 저장 (Stub)
- `suggestCsResponse(context: CsLLMContext): Promise<CsLLMResponse>` - CS 응답 추천 (Stub)

**타입 정의:**
```typescript
export interface CsLLMContext {
  customerInquiry: string;
  ticketHistory?: CsTicket[];
  domain: 'cs';
  language?: string;
  userHints?: Record<string, any>;
}

export interface CsLLMResponse {
  suggestions: CsResponseSuggestion[];
  summary?: string;
  explanation?: string;
}

export interface CsResponseSuggestion {
  response: string;
  confidence?: number;
  category?: string;
}
```

#### 수정 파일: `packages/service-core-cs/src/index.ts`

CS LLM 서비스를 export합니다.

```typescript
export * from './domain/csLLMService.js';
```

### 2. App-Expo

#### 수정 파일: `packages/app-expo/src/hud/engines/types.ts`

CS 도메인 타입을 추가합니다.

```typescript
// CS 도메인 타입 추가
export interface CsLLMContext {
  customerInquiry: string;
  ticketHistory?: any[]; // CsTicket 타입은 별도 import
  domain: 'cs';
  language?: string;
  userHints?: Record<string, any>;
}

export interface CsLLMResponse {
  suggestions: CsResponseSuggestion[];
  summary?: string;
  explanation?: string;
}

export interface CsResponseSuggestion {
  response: string;
  confidence?: number;
  category?: string;
}
```

#### 수정 파일: `packages/app-expo/src/hud/engines/localLLMEngineV1.ts`

CS 도메인 지원을 추가합니다.

```typescript
canHandleDomain(domain: 'accounting' | 'cs'): boolean {
  // CS 도메인 지원 추가
  return domain === 'accounting' || domain === 'cs';
}

async suggest<TPayload = unknown>(
  ctx: SuggestContext,
  input: SuggestInput,
): Promise<SuggestResult<TPayload>> {
  // 도메인별 분기 처리
  if (ctx.domain === 'cs') {
    return this.suggestForCs(ctx, input);
  }
  // 기존 accounting 로직...
}

private async suggestForCs(
  ctx: SuggestContext,
  input: SuggestInput,
): Promise<SuggestResult> {
  // CS 도메인 처리 (Stub)
  // TODO: 실제 LLM 어댑터 연동
  return {
    items: [],
    engine: 'local-llm-v1',
    meta: { type: 'local-llm', label: 'On-device LLM' },
  };
}
```

#### 수정 파일: `packages/app-expo/src/ui/CsHUD.tsx`

SuggestEngine을 사용하도록 수정합니다.

**주요 변경:**
1. `suggestWithEngine` 함수 import
2. "요약/추천" 버튼 추가
3. 버튼 클릭 시 `suggestWithEngine` 호출
4. Mock 모드에서 네트워크 요청 0 유지 확인

**예시 코드:**
```typescript
import { suggestWithEngine } from '../hud/engines/index';
import type { SuggestContext, SuggestInput } from '../hud/engines/types';

// 상태 추가
const [suggesting, setSuggesting] = useState(false);
const [suggestionResult, setSuggestionResult] = useState<any>(null);

// 추천 요청 핸들러
const handleSuggest = async () => {
  setSuggesting(true);
  try {
    const ctx: SuggestContext = {
      domain: 'cs',
      tenantId: clientCfg.tenantId,
      userId: 'hud-user-1',
    };
    
    const input: SuggestInput = {
      text: '고객 문의 내용...', // 실제로는 입력 필드에서 가져옴
      meta: {},
    };
    
    const result = await suggestWithEngine(enginesCfg, ctx, input);
    setSuggestionResult(result);
  } catch (error) {
    console.error('[CS Suggest Error]', error);
  } finally {
    setSuggesting(false);
  }
};

// UI에 버튼 추가
<Button 
  title={suggesting ? "추천 중..." : "요약/추천"} 
  onPress={handleSuggest}
  disabled={suggesting}
/>
```

### 3. Mock 모드 네트워크 0 유지

**확인 사항:**
- `DEMO_MODE=mock`일 때 `suggestWithEngine`이 네트워크 요청을 하지 않는지 확인
- `getSuggestEngine`이 Mock 모드에서 항상 `LocalRuleEngineV1Adapter`를 반환하는지 확인
- E2E 테스트에서 Mock 모드 네트워크 0 검증

## 구현 순서

1. **Service-Core-CS 타입 정의** (`csLLMService.ts` 생성)
   - CS LLM 컨텍스트 타입 정의
   - 인터페이스 skeleton 메서드 구현 (Stub)

2. **App-Expo 엔진 계층 수정**
   - `types.ts`에 CS 타입 추가
   - `localLLMEngineV1.ts`에 CS 도메인 지원 추가

3. **CsHUD 통합**
   - `suggestWithEngine` 사용
   - "요약/추천" 버튼 추가
   - Mock 모드 네트워크 0 확인

4. **테스트**
   - Mock 모드에서 네트워크 요청 0 확인
   - Live 모드에서 엔진 모드별 동작 확인

## 가드레일

- ✅ 회계/기존 OS/HUD 코어 구조 변경 금지
- ✅ `DEMO_MODE=mock`일 때는 `ENGINE_MODE`와 관계없이 네트워크 0 유지
- ✅ 'remote' 모드는 타입/플래그 정의까지만, 실제 원격 호출 구현은 포함하지 않음

