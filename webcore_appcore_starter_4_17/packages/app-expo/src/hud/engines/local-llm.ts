/**
 * LocalLLMEngineV1 구현
 * R8-S2: 실제 온디바이스 엔진 어댑터 Stub
 * 
 * 실제 LLM은 아직 연결하지 않고, 로딩·추론 지연까지 흉내 내는 더미로 구현
 */

import type {
  SuggestEngine,
  SuggestContext,
  SuggestInput,
  SuggestResult,
  SuggestEngineMeta,
  CsSuggestContext,
  CsLLMContext,
  CsLLMResponse,
  CsResponseSuggestion,
} from './types';
import type { ClientCfg } from './index';
import type { SuggestEngine as OldSuggestEngine, SuggestItem as OldSuggestItem } from '../accounting-api';
import { localRuleEngineV1 as oldLocalRuleEngineV1 } from '../accounting-api';
import { getDomainHandler } from './domainHandlers';

export interface LocalLLMEngineOptions {
  cfg: ClientCfg;
}

/**
 * 온디바이스 LLM 어댑터 인터페이스 (R8-S2)
 * 실제 LLM 라이브러리와의 연결을 위한 추상화 계층
 */
export interface OnDeviceLLMAdapter {
  /**
   * 모델 초기화
   */
  initialize(): Promise<void>;
  
  /**
   * 추론 수행
   * @param context LLM 컨텍스트 (도메인, 언어, 힌트 등)
   * @param input 입력 텍스트
   * @returns 추론 결과
   */
  infer(context: {
    domain: 'accounting' | 'cs';
    locale?: string;
    hints?: string[];
  }, input: string): Promise<{
    suggestions: Array<{
      id: string;
      title: string;
      description?: string;
      score: number;
    }>;
    explanation?: string;
  }>;
}

/**
 * 더미 LLM 어댑터 (임시 구현)
 * 실제 LLM 라이브러리 연동 전까지 사용
 */
class DummyLLMAdapter implements OnDeviceLLMAdapter {
  private initialized = false;

  async initialize(): Promise<void> {
    if (this.initialized) return;
    // 모델 로딩 시뮬레이션
    await new Promise((resolve) => setTimeout(resolve, 1500));
    this.initialized = true;
  }

  async infer(context: {
    domain: 'accounting' | 'cs';
    locale?: string;
    hints?: string[];
  }, input: string): Promise<{
    suggestions: Array<{
      id: string;
      title: string;
      description?: string;
      score: number;
    }>;
    explanation?: string;
  }> {
    if (!this.initialized) {
      throw new Error('Adapter not initialized');
    }

    // 추론 지연 시뮬레이션
    await new Promise((resolve) => setTimeout(resolve, 600));

    // 더미 응답 생성
    const label = context.domain === 'accounting' ? '회계' : 'CS';
    return {
      suggestions: [
        {
          id: 'llm-suggestion-1',
          title: `[LLM] ${label} 추론 결과`,
          description: `온디바이스 LLM이 "${input}"을 분석한 결과입니다.`,
          score: 0.85,
        },
      ],
      explanation: `더미 LLM 어댑터가 생성한 추론 결과입니다. 실제 LLM은 R8-S2 이후 연동 예정입니다.`,
    };
  }
}

/**
 * LocalLLMEngineV1
 * 온디바이스 LLM 엔진 구현
 */
export class LocalLLMEngineV1 implements SuggestEngine {
  readonly id = 'local-llm-v1';
  readonly mode = 'local-only' as const;
  
  /**
   * 엔진 메타 정보 (R10-S1)
   * R9-S2 기준: Stub 버전 (local-llm-v0)
   * R10-S2 이후: 실제 모델 연동 시 local-llm-v1로 업그레이드 예정
   */
  private readonly meta: SuggestEngineMeta;
  
  public isReady = false;

  private readonly cfg: ClientCfg;
  private readonly adapter: OnDeviceLLMAdapter;

  constructor(options: LocalLLMEngineOptions) {
    this.cfg = options.cfg;
    // 더미 어댑터 사용 (나중에 실제 LLM 어댑터로 교체 가능)
    this.adapter = new DummyLLMAdapter();
    
    // R10-S1: 엔진 메타 정보 구체화
    this.meta = {
      id: 'local-llm',
      type: 'local-llm',
      label: 'On-device LLM',
      stub: true,                 // 현재는 Stub(v0)
      variant: 'local-llm-v0',
      supportedDomains: ['accounting', 'cs'], // 현재 지원 도메인
    };
    
    // R10-S1: 도메인 핸들러 등록 (초기화 시점에 한 번만)
    this.registerDomainHandlers();
  }

  /**
   * 도메인 핸들러 등록 (R10-S1)
   * 
   * LocalLLMEngineV1의 suggestForCs, suggestForAccounting 로직을 핸들러로 등록
   */
  private registerDomainHandlers(): void {
    // 동적 import로 순환 참조 방지
    import('./domainHandlersRegistry').then(({ registerCsDomainHandler, registerAccountingDomainHandler }) => {
      // CS 도메인 핸들러 등록
      registerCsDomainHandler((ctx) => this.suggestForCs(ctx));
      
      // Accounting 도메인 핸들러 등록 (기존 로직을 래핑)
      registerAccountingDomainHandler(async (ctx, input) => {
        // 기존 accounting 로직 (adapter.infer 사용)
        const llmResult = await this.adapter.infer(
          {
            domain: ctx.domain,
            locale: ctx.locale,
          },
          input.text
        );

        const items = llmResult.suggestions.map((suggestion) => ({
          id: suggestion.id,
          title: suggestion.title,
          description: suggestion.description,
          score: suggestion.score,
          payload: {
            ...suggestion,
            explanation: llmResult.explanation,
          },
          source: 'local-llm' as const,
        }));

        return {
          items,
          engine: 'local-llm-v1',
          confidence: items.length > 0 ? items[0].score : 0.5,
        };
      });
    }).catch((err) => {
      console.warn('[LocalLLMEngineV1] Failed to register domain handlers:', err);
    });
  }

  /**
   * 엔진 메타 정보 조회 (R10-S1)
   * HUD 상태바, OS Dashboard, 로그 등에서 사용
   */
  getMeta(): SuggestEngineMeta {
    return this.meta;
  }

  async initialize(): Promise<void> {
    if (this.isReady) return;
    
    console.log('[LocalLLMEngineV1] loading on-device model (simulated)...');
    await this.adapter.initialize();
    this.isReady = true;
    console.log('[LocalLLMEngineV1] model loaded');
  }

  canHandleDomain(domain: 'accounting' | 'cs'): boolean {
    // R10-S1: CS 도메인 지원 추가
    return domain === 'accounting' || domain === 'cs';
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>> {
    if (!this.isReady) {
      throw new Error('LocalLLMEngineV1 is not ready. Call initialize() first.');
    }

    // R10-S1: 도메인 핸들러 레지스트리 우선 사용
    const handler = getDomainHandler(ctx.domain);
    if (handler) {
      return handler.suggest(ctx, input);
    }

    // 레지스트리에 핸들러가 없으면 기존 분기 로직 사용 (하위 호환성)
    // 1) CS 도메인 우선 처리
    if (ctx.domain === 'cs') {
      return this.suggestForCs(ctx as CsSuggestContext);
    }

    // 2) 기존 accounting 경로 유지
    try {
      // 온디바이스 LLM 추론 수행
      const llmResult = await this.adapter.infer(
        {
          domain: ctx.domain,
          locale: ctx.locale,
        },
        input.text
      );

      // LLM 결과를 SuggestResult 형식으로 변환
      const items = llmResult.suggestions.map((suggestion) => ({
        id: suggestion.id,
        title: suggestion.title,
        description: suggestion.description,
        score: suggestion.score,
        payload: {
          ...suggestion,
          explanation: llmResult.explanation,
        } as TPayload,
        source: 'local-llm' as const,
      }));

      return {
        items,
        engine: 'local-llm-v1',
        confidence: items.length > 0 ? items[0].score : 0.5,
      };
    } catch (error) {
      // LLM 추론 실패 시 fallback 규칙 엔진 사용 (순환 참조 방지를 위해 직접 호출)
      console.warn('[LocalLLMEngineV1] LLM inference failed, falling back to rule engine:', error);
      
      // accounting-api의 localRuleEngineV1을 직접 사용
      const oldInput = {
        description: input.text,
        amount: typeof input.meta?.amount === 'number' ? input.meta.amount : undefined,
        currency: typeof input.meta?.currency === 'string' ? input.meta.currency : undefined,
      };
      
      const oldItems: OldSuggestItem[] = await (oldLocalRuleEngineV1 as OldSuggestEngine).suggest(oldInput);
      
      // 새로운 SuggestItem 형식으로 변환
      const fallbackItems = oldItems.map((item, idx) => ({
        id: item.id || `fallback-${idx}`,
        title: item.description || item.account || 'Unknown',
        description: item.rationale,
        score: item.score,
        payload: {
          ...item,
          account: item.account,
          amount: item.amount,
          currency: item.currency,
          vendor: item.vendor,
          risk: item.risk,
        } as TPayload,
        source: 'local-rule' as const,
      }));
      
      return {
        items: fallbackItems,
        engine: 'local-llm-v1-fallback',
        confidence: oldItems.length > 0 ? oldItems[0].score : 0.5,
      };
    }
  }

  /**
   * R9-S2: CS 도메인용 Local LLM 어댑터
   * - 실제 모델 연동 전까지는 더미 응답 + 지연 시뮬레이션
   * - 네트워크 호출 없음 (온디바이스/Mock 전제)
   */
  private async suggestForCs(ctx: CsSuggestContext): Promise<SuggestResult> {
    // 1) LLM 컨텍스트 구성
    const llmContext: CsLLMContext = {
      tenantId: ctx.tenantId,
      ticketId: ctx.ticket.id,
      subject: ctx.ticket.subject,
      body: ctx.ticket.body,
      history: [
        {
          role: 'user',
          content: ctx.ticket.body,
        },
      ],
    };

    // 2) LLM 추론 지연 시뮬레이션 (사용자 경험 확인용)
    //    - 실제 온디바이스 모델은 수 초 걸릴 수 있으므로, 최소 1.5~2초 정도 대기
    await new Promise((resolve) => setTimeout(resolve, 1800));

    const now = new Date().toISOString();

    const suggestion: CsResponseSuggestion = {
      id: `local-llm-cs-${llmContext.ticketId}-${now}`,
      replyText: [
        '안녕하세요, 고객님.',
        '',
        `${llmContext.subject} 관련 문의를 주셔서 감사합니다.`,
        '현재 상황을 검토해 본 결과, 아래와 같이 안내드릴 수 있습니다.',
        '',
        '1) 설정 화면에서 관련 옵션을 다시 한 번 확인해 주십시오.',
        '2) 그래도 문제가 지속되면, 추가 스크린샷 또는 로그를 첨부해 주시면 더 정확하게 도와드릴 수 있습니다.',
        '',
        '감사합니다.',
      ].join('\n'),
      createdAt: now,
      source: 'local-llm',
    };

    const response: CsLLMResponse = {
      summary: `${llmContext.subject} 문의에 대한 자동 요약입니다.`,
      suggestions: [suggestion],
    };

    // 3) TODO: 이후 R9-S2 후반부 또는 R9-S3에서
    //    - on-device LLM 실제 호출
    //    - recordSuggestionAudit(...) 연동
    //    - usage/token 정보 포함

    // CsLLMResponse를 SuggestResult 형식으로 변환
    const items = response.suggestions.map((s) => ({
      id: s.id,
      title: s.replyText.split('\n')[0] || 'CS 응답 추천',
      description: s.replyText,
      score: 0.85,
      payload: {
        ...s,
        summary: response.summary,
      },
      source: 'local-llm' as const,
    }));

    return {
      items,
      engine: 'local-llm-v1',
      confidence: 0.85,
    };
  }
}

