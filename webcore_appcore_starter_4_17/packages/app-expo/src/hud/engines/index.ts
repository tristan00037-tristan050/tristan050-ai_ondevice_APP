/**
 * SuggestEngine 팩토리 및 유틸리티
 * R8-S1: LocalLLMEngineV1 Stub 연결
 * R8-S2: 엔진 모드 확장 및 메타 정보 추가
 */

import type { SuggestEngine, SuggestContext, SuggestInput, SuggestResult, EngineMode, SuggestEngineMeta } from './types.js';
import { LocalLLMEngineV1 } from './local-llm.js';
import type { SuggestEngine as OldSuggestEngine, SuggestItem as OldSuggestItem, ClientCfg as AccountingClientCfg } from '../accounting-api.js';
import { localRuleEngineV1 as oldLocalRuleEngineV1 } from '../accounting-api.js';
import { isMock } from '../accounting-api.js';

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

  return engine.suggest<TPayload>(ctx, input);
}

