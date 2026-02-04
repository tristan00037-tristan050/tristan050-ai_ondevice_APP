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
    // R9-S2: CS 도메인 지원 추가
    if (ctx.domain === 'cs') {
      return this.suggestForCs(ctx, input);
    }
    
    // 기존 accounting 도메인 처리
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

  /**
   * CS 도메인용 추천 생성 (R9-S2)
   */
  private async suggestForCs(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult> {
    // Stub 구현: 실제 LLM 호출 없이 CS 도메인에 맞는 더미 응답 반환
    const inquiry = input.text || '고객 문의';
    
    return {
      items: [
        {
          id: 'cs-stub-1',
          title: `[Stub] "${inquiry}"에 대한 응답 추천`,
          description: 'R9-S2 초기 단계에서는 인터페이스만 정의합니다. 실제 LLM 연동은 후속 작업에서 진행됩니다.',
          score: 0.5,
          payload: {
            inquiry,
            domain: 'cs',
            ticketId: input.meta?.ticketId,
            status: input.meta?.status,
          },
          source: 'local-llm',
        },
      ],
      engine: 'local-llm-v1',
      confidence: 0.5,
    };
  }
}

