/**
 * SuggestEngine 팩토리 및 유틸리티
 * R8-S1: LocalLLMEngineV1 Stub 연결
 */

import type { SuggestEngine, SuggestContext, SuggestInput, SuggestResult } from './types.js';
import { LocalLLMEngineV1 } from './localLLMEngineV1.js';
import type { SuggestEngine } from './types.js';
import { localRuleEngineV1 } from '../suggestEngineLocal.js';

export interface ClientCfg {
  mode: 'mock' | 'live';
  useLocalLLM?: boolean;
  tenantId: string;
  userId: string;
  baseUrl?: string;
  apiKey?: string;
}

/**
 * SuggestEngine 인스턴스 반환
 */
export function getSuggestEngine(cfg: ClientCfg): SuggestEngine {
  // Mock 모드에서는 항상 로컬 규칙 엔진 사용
  if (cfg.mode === 'mock') {
    return localRuleEngineV1;
  }

  // Live 모드에서 Local LLM 플래그가 켜져 있으면 Stub 사용
  if (cfg.useLocalLLM) {
    return new LocalLLMEngineV1();
  }

  // 기본값: 로컬 규칙 엔진
  return localRuleEngineV1;
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

