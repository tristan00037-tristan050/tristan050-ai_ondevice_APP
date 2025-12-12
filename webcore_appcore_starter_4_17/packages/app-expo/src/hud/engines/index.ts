/**
 * SuggestEngine 팩토리 및 유틸리티
 * R8-S1: LocalLLMEngineV1 Stub 연결
 * R8-S2: 엔진 모드 확장 및 메타 정보 추가
 */

import type { SuggestEngine, SuggestContext, SuggestInput, SuggestResult, EngineMode, SuggestEngineMeta } from './types';
import { LocalLLMEngineV1 } from './local-llm';
import type { SuggestEngine as OldSuggestEngine, SuggestItem as OldSuggestItem, ClientCfg as AccountingClientCfg } from '../accounting-api';
import { localRuleEngineV1 as oldLocalRuleEngineV1 } from '../accounting-api';
import { isMock } from '../accounting-api';
import { applyLlmTextPostProcess } from './llmPostProcess';

/**
 * SuggestEngine용 ClientCfg (accounting-api의 ClientCfg를 확장)
 */
export interface ClientCfg extends AccountingClientCfg {
  userId?: string; // engines 계층에서 필요할 수 있는 추가 필드
}

/**
 * 기존 localRuleEngineV1을 새로운 SuggestEngine 인터페이스에 맞게 어댑터로 래핑
 */
export class LocalRuleEngineV1Adapter implements SuggestEngine {
  readonly id = 'local-rule-v1';
  readonly mode = 'local-only' as const;
  
  public meta: SuggestEngineMeta;
  public isReady = true; // 규칙 엔진은 항상 준비됨

  constructor(options?: { cfg?: ClientCfg; mode?: EngineMode }) {
    const mode = options?.mode || 'rule';
    this.meta = {
      type: mode === 'mock' ? 'mock' : 'rule',
      label: mode === 'mock' ? 'Mock' : 'On-device (Rule)',
    };
  }
  
  async initialize?(): Promise<void> {
    // 규칙 엔진은 초기화 불필요
    return Promise.resolve();
  }

  canHandleDomain(domain: 'accounting' | 'cs'): boolean {
    // R9-S2: CS 도메인 지원 추가
    return domain === 'accounting' || domain === 'cs';
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>> {
    // R9-S2: CS 도메인 처리 추가
    if (ctx.domain === 'cs') {
      return this.suggestForCs(ctx, input);
    }

    // 기존 accounting 도메인 처리
    const oldInput = {
      description: input.text,
      amount: typeof input.meta?.amount === 'number' ? input.meta.amount : undefined,
      currency: typeof input.meta?.currency === 'string' ? input.meta.currency : undefined,
    };

    const oldItems: OldSuggestItem[] = await (oldLocalRuleEngineV1 as OldSuggestEngine).suggest(oldInput);

    // 새로운 SuggestItem 형식으로 변환
    const newItems = oldItems.map((item, idx) => {
      const rawTitle = item.description || item.account || 'Unknown';
      // R10-S2: HUD 레벨 후처리 적용
      const processedTitle = applyLlmTextPostProcess(
        {
          domain: ctx.domain,
          engineMeta: this.meta,
          mode: this.meta.type,
        },
        rawTitle,
      );
      const processedDescription = item.rationale
        ? applyLlmTextPostProcess(
            {
              domain: ctx.domain,
              engineMeta: this.meta,
              mode: this.meta.type,
            },
            item.rationale,
          )
        : undefined;

      return {
        id: item.id || `item-${idx}`,
        title: processedTitle,
        description: processedDescription,
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
      };
    });

    return {
      items: newItems,
      engine: 'local-rule-v1',
      confidence: oldItems.length > 0 ? oldItems[0].score : 0.5,
    };
  }

  /**
   * CS 도메인용 추천 생성 (R9-S2)
   */
  private async suggestForCs(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult> {
    // Mock/Rule 모드에서 CS 도메인에 대한 더미 응답 반환
    const inquiry = input.text || '고객 문의';
    const rawTitle = `[Rule] "${inquiry}" 문의에 대한 규칙 기반 Mock 응답입니다.`;
    const rawDescription = 'Mock/Rule 모드에서는 간단한 규칙 기반 응답을 제공합니다.';
    
    // R10-S2: HUD 레벨 후처리 적용
    const processedTitle = applyLlmTextPostProcess(
      {
        domain: ctx.domain,
        engineMeta: this.meta,
        mode: this.meta.type,
      },
      rawTitle,
    );
    const processedDescription = applyLlmTextPostProcess(
      {
        domain: ctx.domain,
        engineMeta: this.meta,
        mode: this.meta.type,
      },
      rawDescription,
    );
    
    return {
      items: [
        {
          id: 'cs-rule-1',
          title: processedTitle,
          description: processedDescription,
          score: 0.5,
          payload: {
            inquiry,
            domain: 'cs',
            ticketId: input.meta?.ticketId,
            status: input.meta?.status,
          },
          source: 'local-rule',
        },
      ],
      engine: 'local-rule-v1',
      confidence: 0.5,
    };
  }
}

/**
 * 환경 변수에서 엔진 모드 결정 (R8-S2)
 */
function getEngineModeFromEnv(): EngineMode {
  const raw = process.env.EXPO_PUBLIC_ENGINE_MODE ?? 'rule';

  if (raw === 'mock') return 'mock';
  if (raw === 'local-llm') return 'local-llm';
  if (raw === 'remote') return 'remote';
  return 'rule';
}

/**
 * SuggestEngine 인스턴스 반환
 */
export function getSuggestEngine(cfg: ClientCfg): SuggestEngine {
  const mode = getEngineModeFromEnv();
  const demoMode = cfg.mode === 'mock' ? 'mock' : 'live';

  // Mock 모드에서는 항상 mock 엔진 사용 (불변 조건)
  if (demoMode === 'mock') {
    return new LocalRuleEngineV1Adapter({ cfg, mode: 'mock' });
  }

  // Live 모드에서 엔진 모드에 따라 선택
  if (mode === 'local-llm') {
    const engine = new LocalLLMEngineV1({ cfg });
    // initialize는 HUD 쪽에서 호출할 수 있도록 남겨둠
    return engine;
  }

  if (mode === 'rule' || mode === 'mock') {
    return new LocalRuleEngineV1Adapter({ cfg, mode: 'rule' });
  }

  // remote 모드는 아직 rule 엔진으로 포워딩
  if (mode === 'remote') {
    return new LocalRuleEngineV1Adapter({ cfg, mode: 'rule' });
  }

  // 기본값: rule 엔진
  return new LocalRuleEngineV1Adapter({ cfg, mode: 'rule' });
}

/**
 * SuggestEngine을 사용하여 추천 요청
 */
export async function suggestWithEngine<TPayload = unknown>(
  cfg: ClientCfg,
  ctx: SuggestContext,
  input: SuggestInput,
): Promise<SuggestResult<TPayload>> {
  const engine = getSuggestEngine(cfg);
  
  if (!engine.canHandleDomain(ctx.domain)) {
    throw new Error(`Engine ${engine.id} does not support domain: ${ctx.domain}`);
  }

  // 엔진이 초기화되지 않았으면 자동으로 초기화
  if (!engine.isReady && engine.initialize) {
    await engine.initialize();
  }

  return engine.suggest<TPayload>(ctx, input);
}

