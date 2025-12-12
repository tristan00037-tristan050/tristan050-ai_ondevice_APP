/**
 * CS LLM Service
 * R9-S2: CS 도메인 LLM 서비스 스켈레톤
 * R10-S1: DomainLLMService 인터페이스 구현
 * 
 * @module service-core-cs/domain/csLLMService
 */

import type { DomainLLMService } from './domainLLMService.js';

/**
 * CS LLM 컨텍스트
 */
export interface CsLLMContext {
  tenantId: string;
  ticketId: string;
  subject: string;
  body: string;
  history: Array<{
    role: 'user' | 'agent' | 'system';
    content: string;
  }>;
}

/**
 * CS LLM 응답
 */
export interface CsLLMResponse {
  summary?: string;
  suggestions: Array<{
    id: string;
    replyText: string;
    createdAt: string; // ISO string
    source: 'rule' | 'local-llm' | 'remote-llm';
  }>;
}

/**
 * CS 티켓 (입력 타입)
 */
export interface CsTicket {
  id: string;
  subject: string;
  body: string;
  status: string;
  createdAt: string;
}

/**
 * CS 히스토리 아이템 (입력 타입)
 */
export interface CsHistoryItem {
  role: 'user' | 'agent' | 'system';
  content: string;
}

/**
 * CS LLM Service 구현
 * 
 * DomainLLMService 인터페이스를 구현하여 CS 도메인 LLM 패턴을 제공
 */
export class CsLLMService implements DomainLLMService<CsLLMContext, CsLLMResponse> {
  /**
   * LLM 컨텍스트 구성
   * 
   * @param ticket - CS 티켓
   * @param history - CS 히스토리 (선택)
   * @returns CS LLM 컨텍스트
   */
  async buildContext(
    ticket: CsTicket,
    history: CsHistoryItem[] = []
  ): Promise<CsLLMContext> {
    return {
      tenantId: ticket.id.split('-')[0] || 'default', // 임시: ticketId에서 tenant 추출
      ticketId: ticket.id,
      subject: ticket.subject,
      body: ticket.body,
      history: history.length > 0 
        ? history 
        : [
            {
              role: 'user',
              content: ticket.body,
            },
          ],
    };
  }

  /**
   * LLM 프롬프트 생성
   * 
   * @param ctx - CS LLM 컨텍스트
   * @returns 프롬프트 문자열
   */
  buildPrompt(ctx: CsLLMContext): string {
    const historyText = ctx.history
      .map((item) => `${item.role}: ${item.content}`)
      .join('\n');

    return `You are a customer service agent. Please provide a helpful response to the following customer inquiry.

Ticket: ${ctx.subject}
Customer Message: ${ctx.body}

${historyText ? `\nPrevious conversation:\n${historyText}` : ''}

Please provide a professional, helpful response in Korean.`;
  }

  /**
   * LLM 사용 감사(Audit) 기록
   * 
   * @param ctx - CS LLM 컨텍스트
   * @param res - CS LLM 응답
   * @returns Promise<void>
   */
  async recordAudit(ctx: CsLLMContext, res: CsLLMResponse): Promise<void> {
    // R10-S1: Stub 구현 (로그만 기록)
    // R10-S2 이후: 실제 DB 적재 또는 이벤트 전송
    console.log('[CsLLMService] Audit record:', {
      tenantId: ctx.tenantId,
      ticketId: ctx.ticketId,
      suggestionCount: res.suggestions.length,
      timestamp: new Date().toISOString(),
    });
  }
}

/**
 * CS LLM Service 싱글톤 인스턴스
 */
export const csLLMService = new CsLLMService();

