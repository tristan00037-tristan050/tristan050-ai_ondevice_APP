/**
 * 도메인 핸들러 등록 모듈
 * R10-S1: CS/Accounting 핸들러 등록 예시
 * 
 * @module app-expo/hud/engines/domainHandlersRegistry
 */

import { registerDomainHandler } from './domainHandlers';
import type { SuggestContext, SuggestInput, SuggestResult } from './types';
import type { CsSuggestContext, CsLLMContext, CsLLMResponse, CsResponseSuggestion } from './types';

/**
 * CS 도메인 핸들러 등록
 * 
 * LocalLLMEngineV1의 suggestForCs 로직을 핸들러로 분리
 */
export function registerCsDomainHandler(
  suggestForCs: (ctx: CsSuggestContext) => Promise<SuggestResult>
): void {
  registerDomainHandler({
    domain: 'cs',
    suggest: async (ctx: SuggestContext, input: SuggestInput): Promise<SuggestResult> => {
      // CsSuggestContext로 변환
      const csCtx: CsSuggestContext = {
        domain: 'cs',
        tenantId: ctx.tenantId,
        ticket: {
          id: input.meta?.ticketId as string || 'unknown',
          subject: input.text,
          body: input.meta?.body as string || input.text,
          status: input.meta?.status as string || 'open',
          createdAt: input.meta?.createdAt as string || new Date().toISOString(),
        },
      };
      
      return suggestForCs(csCtx);
    },
  });
}

/**
 * Accounting 도메인 핸들러 등록
 * 
 * LocalLLMEngineV1의 accounting 로직을 핸들러로 분리
 */
export function registerAccountingDomainHandler(
  suggestForAccounting: (ctx: SuggestContext, input: SuggestInput) => Promise<SuggestResult>
): void {
  registerDomainHandler({
    domain: 'accounting',
    suggest: async (ctx: SuggestContext, input: SuggestInput): Promise<SuggestResult> => {
      return suggestForAccounting(ctx, input);
    },
  });
}

