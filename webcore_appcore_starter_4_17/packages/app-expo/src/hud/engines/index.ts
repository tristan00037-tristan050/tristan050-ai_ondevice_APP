/**
 * SuggestEngine 팩토리 및 유틸리티
 * R8-S1: LocalLLMEngineV1 Stub 연결
 */

import type { SuggestEngine, SuggestContext, SuggestInput, SuggestResult } from './types.js';
import { LocalLLMEngineV1 } from './localLLMEngineV1.js';
import type { SuggestEngine as OldSuggestEngine, SuggestItem as OldSuggestItem } from '../accounting-api.js';
import { localRuleEngineV1 as oldLocalRuleEngineV1 } from '../accounting-api.js';
import { isMock } from '../accounting-api.js';

export interface ClientCfg {
  mode: 'mock' | 'live';
  useLocalLLM?: boolean;
  tenantId: string;
  userId: string;
  baseUrl?: string;
  apiKey?: string;
}

/**
 * 기존 localRuleEngineV1을 새로운 SuggestEngine 인터페이스에 맞게 어댑터로 래핑
 */
class LocalRuleEngineV1Adapter implements SuggestEngine {
  readonly id = 'local-rule-v1';
  readonly mode = 'local-only' as const;

  canHandleDomain(domain: 'accounting' | 'cs'): boolean {
    // 기존 localRuleEngineV1은 accounting 도메인만 지원
    return domain === 'accounting';
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>> {
    // 기존 localRuleEngineV1의 suggest 메서드 호출
    const oldInput = {
      description: input.text,
      amount: typeof input.meta?.amount === 'number' ? input.meta.amount : undefined,
      currency: typeof input.meta?.currency === 'string' ? input.meta.currency : undefined,
    };

    const oldItems: OldSuggestItem[] = await (oldLocalRuleEngineV1 as OldSuggestEngine).suggest(oldInput);

    // 새로운 SuggestItem 형식으로 변환
    const newItems = oldItems.map((item, idx) => ({
      id: item.id || `item-${idx}`,
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
      items: newItems,
      engine: 'local-rule-v1',
      confidence: oldItems.length > 0 ? oldItems[0].score : 0.5,
    };
  }
}

// 싱글톤 인스턴스
const localRuleEngineV1Adapter = new LocalRuleEngineV1Adapter();

/**
 * SuggestEngine 인스턴스 반환
 */
export function getSuggestEngine(cfg: ClientCfg): SuggestEngine {
  // Mock 모드에서는 항상 로컬 규칙 엔진 사용
  if (cfg.mode === 'mock') {
    return localRuleEngineV1Adapter;
  }

  // Live 모드에서 Local LLM 플래그가 켜져 있으면 Stub 사용
  if (cfg.useLocalLLM) {
    return new LocalLLMEngineV1();
  }

  // 기본값: 로컬 규칙 엔진
  return localRuleEngineV1Adapter;
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

  return engine.suggest<TPayload>(ctx, input);
}

