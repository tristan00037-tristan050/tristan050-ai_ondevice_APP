# R10-S2 구현 가이드

## 개요

R10-S2 스프린트의 각 티켓에 대한 구체적인 구현 가이드입니다.

## [R10S2-SC12-1] DomainLLMService 공통 패키지 승격

### 1. 공통 패키지 구조 확인

먼저 `service-core-common` 패키지가 존재하는지 확인:

```bash
ls -la packages/service-core-common
```

없다면 생성:

```bash
mkdir -p packages/service-core-common/src/llm
```

### 2. DomainLLMService 인터페이스 생성

**파일:** `packages/service-core-common/src/llm/domainLLMService.ts`

```typescript
/**
 * Domain LLM Service 공통 인터페이스
 * R10-S2: 회계/CS/HR/법무/보안이 같은 패턴으로 움직이도록 강제
 * 
 * @module service-core-common/llm/domainLLMService
 */

export interface DomainLLMService<TContext, TResponse> {
  /**
   * LLM 컨텍스트 구성
   */
  buildContext(...args: any[]): Promise<TContext> | TContext;

  /**
   * LLM 프롬프트 생성
   */
  buildPrompt(ctx: TContext): string;

  /**
   * LLM 사용 감사 기록
   */
  recordAudit(ctx: TContext, res: TResponse): Promise<void>;

  /**
   * LLM 응답 후처리 (선택사항)
   * 개인정보 마스킹, 금지 표현 필터링 등
   */
  postProcess?(ctx: TContext, res: TResponse): Promise<TResponse> | TResponse;
}
```

### 3. package.json 확인 및 수정

`packages/service-core-common/package.json`이 있다면 확인, 없다면 생성:

```json
{
  "name": "@appcore/service-core-common",
  "version": "0.1.0",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": "./dist/index.js",
    "./llm/domainLLMService": "./dist/llm/domainLLMService.js"
  }
}
```

### 4. csLLMService 수정

**파일:** `packages/service-core-cs/src/domain/csLLMService.ts`

```typescript
// 기존 import 제거
// import type { DomainLLMService } from './domainLLMService';

// 공통 인터페이스 import
import type { DomainLLMService } from '@appcore/service-core-common/llm/domainLLMService';

// 나머지 코드는 그대로 유지
export class CsLLMService implements DomainLLMService<CsLLMContext, CsLLMResponse> {
  // ... 기존 구현 ...
  
  // R10-S2: postProcess 추가
  async postProcess(ctx: CsLLMContext, res: CsLLMResponse): Promise<CsLLMResponse> {
    // 기본 구현: 개인정보 마스킹 등
    // TODO: 실제 후처리 로직 구현
    return res;
  }
}
```

### 5. 기존 domainLLMService.ts 삭제

```bash
rm packages/service-core-cs/src/domain/domainLLMService.ts
```

### 6. 타입 체크 및 빌드

```bash
npm run typecheck --workspace=@appcore/service-core-common
npm run typecheck --workspace=@appcore/service-core-cs
npm run build --workspace=@appcore/service-core-common
npm run build --workspace=@appcore/service-core-cs
```

---

## [R10S2-A13-1] LLM Usage eventType 추가

### 1. llmUsage.ts 수정

**파일:** `packages/app-expo/src/hud/telemetry/llmUsage.ts`

```typescript
import { mkHeaders } from '../accounting-api';
import type { ClientCfg } from '../accounting-api';
import type { EngineMode, EngineMeta, SuggestDomain } from '../engines/types';

// R10-S2: eventType 추가
export type LlmUsageEventType =
  | 'shown'              // 추천 패널 표시
  | 'accepted_as_is'    // 그대로 사용
  | 'edited'             // 수정 후 전송
  | 'rejected'           // 추천 닫기/무시
  | 'error';             // 엔진 에러

export interface LlmUsageEvent {
  tenantId: string;
  userId: string;
  domain: SuggestDomain;
  engineId: string;
  engineVariant?: string;
  engineMode: EngineMode;
  engineStub?: boolean;
  eventType: LlmUsageEventType;  // R10-S2: 추가
  feature: string;
  timestamp: string;
  suggestionLength: number;
}

export async function sendLlmUsageEvent(
  cfg: ClientCfg,
  meta: EngineMeta,
  evt: Omit<LlmUsageEvent, 'engineId' | 'engineVariant' | 'engineMode' | 'engineStub'>,
) {
  const payload: LlmUsageEvent = {
    ...evt,
    engineId: meta.id,
    engineVariant: meta.variant,
    engineMode: meta.mode,
    engineStub: meta.stub,
  };

  if (cfg.mode === 'mock') {
    console.log('[MOCK] LLM usage event', payload);
    return;
  }

  await fetch(`${cfg.baseUrl}/v1/os/llm-usage`, {
    method: 'POST',
    headers: mkHeaders(cfg),
    body: JSON.stringify(payload),
  });
}
```

### 2. CsHUD.tsx 수정

**파일:** `packages/app-expo/src/ui/CsHUD.tsx`

```typescript
import { sendLlmUsageEvent } from '../hud/telemetry/llmUsage';
import type { LlmUsageEventType } from '../hud/telemetry/llmUsage';

// 추천 완료 후
const handleSuggest = async () => {
  try {
    setSuggesting(true);
    const result = await suggestWithEngine(clientCfg, ctx, input);
    setSuggestionResult(result);
    
    // R10-S2: shown 이벤트 전송
    const meta = engine.getMeta();
    await sendLlmUsageEvent(clientCfg, meta, {
      tenantId: clientCfg.tenantId!,
      userId: clientCfg.userId!,
      domain: 'cs',
      eventType: 'shown',  // R10-S2: 추가
      feature: 'cs_reply_suggest',
      timestamp: new Date().toISOString(),
      suggestionLength: result.items[0]?.title?.length || 0,
    });
  } catch (error) {
    // R10-S2: error 이벤트 전송
    const meta = engine.getMeta();
    await sendLlmUsageEvent(clientCfg, meta, {
      tenantId: clientCfg.tenantId!,
      userId: clientCfg.userId!,
      domain: 'cs',
      eventType: 'error',  // R10-S2: 추가
      feature: 'cs_reply_suggest',
      timestamp: new Date().toISOString(),
      suggestionLength: 0,
    });
  } finally {
    setSuggesting(false);
  }
};

// "그대로 사용" 버튼 클릭 시
const handleAcceptAsIs = async () => {
  const meta = engine.getMeta();
  await sendLlmUsageEvent(clientCfg, meta, {
    tenantId: clientCfg.tenantId!,
    userId: clientCfg.userId!,
    domain: 'cs',
    eventType: 'accepted_as_is',  // R10-S2: 추가
    feature: 'cs_reply_suggest',
    timestamp: new Date().toISOString(),
    suggestionLength: suggestionResult?.items[0]?.title?.length || 0,
  });
  // ... 나머지 로직 ...
};

// 수정 후 전송 시
const handleEdited = async () => {
  const meta = engine.getMeta();
  await sendLlmUsageEvent(clientCfg, meta, {
    tenantId: clientCfg.tenantId!,
    userId: clientCfg.userId!,
    domain: 'cs',
    eventType: 'edited',  // R10-S2: 추가
    feature: 'cs_reply_suggest',
    timestamp: new Date().toISOString(),
    suggestionLength: editedText.length,
  });
  // ... 나머지 로직 ...
};

// 추천 닫기/무시 시
const handleReject = async () => {
  const meta = engine.getMeta();
  await sendLlmUsageEvent(clientCfg, meta, {
    tenantId: clientCfg.tenantId!,
    userId: clientCfg.userId!,
    domain: 'cs',
    eventType: 'rejected',  // R10-S2: 추가
    feature: 'cs_reply_suggest',
    timestamp: new Date().toISOString(),
    suggestionLength: suggestionResult?.items[0]?.title?.length || 0,
  });
  // ... 나머지 로직 ...
};
```

### 3. BFF os-llm-usage.ts 수정

**파일:** `packages/bff-accounting/src/routes/os-llm-usage.ts`

```typescript
// ... 기존 코드 ...

osLlmUsageRouter.post(
  '/v1/os/llm-usage',
  requireTenantAuth,
  async (req, res, next) => {
    try {
      const tenantId = (req as any).tenantId || req.body.tenantId;
      const userId = req.headers['x-user-id'] as string || req.body.userId;
      const userRole = req.headers['x-user-role'] as string || 'operator';
      const body = req.body as {
        domain: string;
        engineId: string;
        engineVariant?: string;
        engineMode: string;
        engineStub?: boolean;
        eventType: string;  // R10-S2: 추가
        outcome: string;
        feature: string;
        timestamp: string;
        suggestionLength: number;
      };

      const logEvent = {
        type: 'llm_usage',
        tenant: tenantId,
        userId,
        userRole,
        ...body,
        ts: new Date().toISOString(),
      };

      console.log(JSON.stringify(logEvent));
      res.status(204).end();
    } catch (err) {
      next(err);
    }
  },
);
```

---

## [R10S2-S12-1] Remote LLM Gateway 라우트 설계

### 1. os-llm-gateway.ts 생성

**파일:** `packages/bff-accounting/src/routes/os-llm-gateway.ts`

```typescript
/**
 * Remote LLM Gateway 라우트
 * R10-S2: HUD가 외부 LLM을 직접 호출하지 않고, OS Gateway를 통해 나가는 레일 확보
 * 
 * @module bff-accounting/routes/os-llm-gateway
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';

export const osLlmGatewayRouter = Router();

/**
 * POST /v1/os/llm/proxy
 * Remote LLM Gateway 프록시
 * 
 * 현재는 501 Not Implemented 반환
 * 실제 LLM 호출은 R10-S3 이후 구현 예정
 */
osLlmGatewayRouter.post(
  '/v1/os/llm/proxy',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.tenantId || req.headers['x-tenant'] as string;
      const body = req.body as {
        domain: string;
        engineId: string;
        prompt: string;
        metadata?: Record<string, any>;
      };

      // TODO: 데이터 등급/정책 필터 (R10-S3 이후)
      // TODO: 외부/사내 LLM 호출 래퍼 (현재는 Stub or 501 Not Implemented)

      // R10-S2: 현재는 501 Not Implemented 반환
      return res.status(501).json({
        error_code: 'not_implemented',
        message: 'Remote LLM gateway is not yet implemented. This will be available in R10-S3.',
        tenant,
        requestedDomain: body.domain,
        requestedEngine: body.engineId,
      });
    } catch (err) {
      next(err);
    }
  }
);

export default osLlmGatewayRouter;
```

### 2. BFF index.ts에 라우트 등록

**파일:** `packages/bff-accounting/src/index.ts`

```typescript
// ... 기존 import ...
import osLlmGatewayRoute from './routes/os-llm-gateway.js';

// ... 기존 코드 ...

app.use(osLlmUsageRoute);
app.use(osLlmGatewayRoute);  // R10-S2: 추가
```

---

## [R10S2-E05-1] LLM 응답 후처리 Hook 연동

### 1. LocalLLMEngineV1 수정

**파일:** `packages/app-expo/src/hud/engines/local-llm.ts`

```typescript
// ... 기존 코드 ...

async suggest<TPayload = unknown>(
  ctx: SuggestContext,
  input: SuggestInput,
): Promise<SuggestResult<TPayload>> {
  // ... 기존 LLM 추론 로직 ...
  
  const rawRes = await this.adapter.infer(
    {
      domain: ctx.domain,
      locale: ctx.locale,
    },
    input.text
  );

  // R10-S2: 도메인 서비스에서 postProcess 호출
  let finalRes = rawRes;
  
  if (ctx.domain === 'cs') {
    // CS 도메인 서비스 가져오기
    const { csLLMService } = await import('@appcore/service-core-cs');
    const domainService = csLLMService;
    
    // LLM 컨텍스트 구성
    const llmContext = await domainService.buildContext(ctx.ticket, ctx.history);
    
    // 후처리 Hook 호출
    if (domainService.postProcess) {
      finalRes = await domainService.postProcess(llmContext, rawRes);
    }
    
    // 감사 기록
    await domainService.recordAudit(llmContext, finalRes);
  }
  
  // ... 나머지 변환 로직 ...
}
```

### 2. csLLMService에 postProcess 구현

**파일:** `packages/service-core-cs/src/domain/csLLMService.ts`

```typescript
// ... 기존 코드 ...

async postProcess(ctx: CsLLMContext, res: CsLLMResponse): Promise<CsLLMResponse> {
  // 기본 구현: 개인정보 마스킹 등
  // TODO: 실제 후처리 로직 구현
  
  // 예시: 이메일 주소 마스킹
  const maskedSuggestions = res.suggestions.map(suggestion => ({
    ...suggestion,
    replyText: suggestion.replyText.replace(
      /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,
      '[EMAIL_MASKED]'
    ),
  }));
  
  return {
    ...res,
    suggestions: maskedSuggestions,
  };
}
```

---

## 테스트 체크리스트

### Mock 모드 테스트

```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```

체크 항목:
- [ ] 콘솔에 `[MOCK] LLM usage event` 로그 출력
- [ ] `eventType: 'shown'` 포함
- [ ] "그대로 사용" 클릭 시 `eventType: 'accepted_as_is'` 출력
- [ ] 수정 후 전송 시 `eventType: 'edited'` 출력
- [ ] 추천 닫기 시 `eventType: 'rejected'` 출력

### Live 모드 테스트

```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```

체크 항목:
- [ ] BFF 로그에 `{"type":"llm_usage", "eventType":"shown", ...}` JSON 출력
- [ ] `/v1/os/llm-usage` 204 응답
- [ ] `/v1/os/llm/proxy` 501 응답 (Remote Gateway)

---

## 커밋 전략

각 티켓별로 커밋:

```bash
# [R10S2-SC12-1]
git add packages/service-core-common packages/service-core-cs
git commit -m "feat(r10-s2): promote DomainLLMService to common package"

# [R10S2-A13-1]
git add packages/app-expo/src/hud/telemetry packages/app-expo/src/ui/CsHUD.tsx
git commit -m "feat(r10-s2): add eventType to LLM usage events"

# [R10S2-S12-1]
git add packages/bff-accounting/src/routes/os-llm-gateway.ts
git commit -m "feat(r10-s2): add remote LLM gateway route (501 stub)"

# [R10S2-E05-1]
git add packages/app-expo/src/hud/engines packages/service-core-cs
git commit -m "feat(r10-s2): add LLM response post-processing hook"
```

