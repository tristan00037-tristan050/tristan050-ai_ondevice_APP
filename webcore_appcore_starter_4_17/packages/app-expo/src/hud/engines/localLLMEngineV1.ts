/**
 * LocalLLMEngineV1 Stub
 * R8-S1: 인터페이스와 흐름만 검증, 실제 LLM은 R8-S2 이후
 * R8-S2: A09-2에서 실제 구현으로 교체 예정
 */

import type {
  SuggestEngine,
  SuggestContext,
  SuggestInput,
  SuggestResult,
  SuggestEngineMeta,
} from './types';

export class LocalLLMEngineV1 implements SuggestEngine {
  readonly id = 'local-llm-v1';
  readonly mode = 'local-only' as const;
  
  public meta: SuggestEngineMeta = {
    type: 'local-llm',
    label: 'On-device LLM',
  };
  
  public isReady = false; // A09-2에서 initialize() 구현 예정

  canHandleDomain(_domain: 'accounting' | 'cs'): boolean {
    return true; // 스켈레톤 단계에서는 모든 도메인 지원으로 둔다.
  }
  
  async initialize(): Promise<void> {
    // A09-2에서 실제 구현 예정
    this.isReady = true;
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>> {
    // R8-S1에서는 네트워크 호출 없이 간단한 더미 응답만 생성한다.
    const label = ctx.domain === 'accounting' ? '회계' : 'CS';

    return {
      items: [
        {
          id: 'stub-1',
          title: `[Stub] ${label}용 Local LLM 엔진 자리`,
          description:
            'R8-S1에서는 인터페이스와 흐름만 검증합니다. 실제 LLM은 이후 스프린트에서 붙입니다.',
          score: 0.5,
          payload: undefined as TPayload,
          source: 'local-llm',
        },
      ],
      engine: 'local-llm-v1',
      confidence: 0.5,
    };
  }
}

