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
} from './types';
import type { ClientCfg } from './index';
import { LocalRuleEngineV1Adapter } from './index';

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
  
  public meta: SuggestEngineMeta = {
    type: 'local-llm',
    label: 'On-device LLM',
  };
  
  public isReady = false;

  private readonly cfg: ClientCfg;
  private readonly adapter: OnDeviceLLMAdapter;
  private readonly fallbackRuleEngine: LocalRuleEngineV1Adapter;

  constructor(options: LocalLLMEngineOptions) {
    this.cfg = options.cfg;
    // 더미 어댑터 사용 (나중에 실제 LLM 어댑터로 교체 가능)
    this.adapter = new DummyLLMAdapter();
    // 추론 품질이 충분하지 않을 때를 대비해 rule 엔진을 fallback으로 사용
    this.fallbackRuleEngine = new LocalRuleEngineV1Adapter({
      cfg: this.cfg,
      mode: 'rule',
    });
  }

  async initialize(): Promise<void> {
    if (this.isReady) return;
    
    console.log('[LocalLLMEngineV1] loading on-device model (simulated)...');
    await this.adapter.initialize();
    this.isReady = true;
    console.log('[LocalLLMEngineV1] model loaded');
  }

  canHandleDomain(domain: 'accounting' | 'cs'): boolean {
    // 현재는 accounting만 지원 (CS는 계속 Stub)
    return domain === 'accounting';
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>> {
    if (!this.isReady) {
      throw new Error('LocalLLMEngineV1 is not ready. Call initialize() first.');
    }

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
      // LLM 추론 실패 시 fallback 규칙 엔진 사용
      console.warn('[LocalLLMEngineV1] LLM inference failed, falling back to rule engine:', error);
      return this.fallbackRuleEngine.suggest<TPayload>(ctx, input);
    }
  }
}

