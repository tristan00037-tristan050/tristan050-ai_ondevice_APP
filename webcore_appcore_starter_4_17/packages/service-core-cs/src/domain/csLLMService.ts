/**
 * CS LLM Service Domain Logic
 * R9-S2: CS 도메인에 온디바이스 LLM 연동을 위한 인터페이스 skeleton
 * 
 * @module service-core-cs/domain/csLLMService
 */

import type { CsTicket } from './csTickets.js';

/**
 * CS LLM 컨텍스트 (LLM 입력 형식)
 */
export interface CsLLMContext {
  customerInquiry: string;
  ticketHistory?: CsTicket[];
  domain: 'cs';
  language?: string;
  userHints?: Record<string, any>;
}

/**
 * CS 응답 추천 항목
 */
export interface CsResponseSuggestion {
  response: string;
  confidence?: number;
  category?: string;
}

/**
 * CS LLM 응답 (LLM 출력 형식)
 */
export interface CsLLMResponse {
  suggestions: CsResponseSuggestion[];
  summary?: string;
  explanation?: string;
}

/**
 * 티켓을 LLM 입력 형식으로 변환
 * 
 * @param ticket - CS 티켓
 * @returns LLM 컨텍스트
 */
export function getTicketSummaryLLMInput(ticket: CsTicket): CsLLMContext {
  return {
    customerInquiry: ticket.subject,
    domain: 'cs',
    language: 'ko', // 기본값: 한국어
    userHints: {
      ticketId: ticket.id,
      status: ticket.status,
      createdAt: ticket.createdAt.toISOString(),
    },
  };
}

/**
 * 티켓 히스토리를 포함한 LLM 컨텍스트 생성
 * 
 * @param currentTicket - 현재 티켓
 * @param history - 티켓 히스토리 (선택)
 * @returns LLM 컨텍스트
 */
export function buildCsLLMContext(
  currentTicket: CsTicket,
  history?: CsTicket[],
): CsLLMContext {
  return {
    customerInquiry: currentTicket.subject,
    ticketHistory: history,
    domain: 'cs',
    language: 'ko',
    userHints: {
      ticketId: currentTicket.id,
      status: currentTicket.status,
      createdAt: currentTicket.createdAt.toISOString(),
    },
  };
}

/**
 * CS 응답 추천 생성 (Stub)
 * 
 * 실제 LLM 호출은 R9-S2 후반 또는 다음 스프린트에서 구현 예정
 * 
 * @param context - CS LLM 컨텍스트
 * @returns CS LLM 응답
 */
export async function suggestCsResponse(
  context: CsLLMContext,
): Promise<CsLLMResponse> {
  // Stub 구현: 실제 LLM 호출 없이 더미 응답 반환
  return {
    suggestions: [
      {
        response: `[Stub] 고객 문의 "${context.customerInquiry}"에 대한 응답 추천이 여기에 표시됩니다.`,
        confidence: 0.5,
        category: 'general',
      },
    ],
    summary: `[Stub] 고객 문의 요약: ${context.customerInquiry}`,
    explanation: 'R9-S2 초기 단계에서는 인터페이스만 정의합니다. 실제 LLM 연동은 후속 작업에서 진행됩니다.',
  };
}

/**
 * 응답 추천 프롬프트 생성
 * 
 * @param context - CS LLM 컨텍스트
 * @returns LLM 프롬프트 문자열
 */
export function buildReplyPrompt(context: CsLLMContext): string {
  const inquiry = context.customerInquiry;
  const history = context.ticketHistory || [];
  
  let prompt = `고객 문의: ${inquiry}\n\n`;
  
  if (history.length > 0) {
    prompt += `이전 대화 히스토리:\n`;
    history.forEach((ticket, idx) => {
      prompt += `${idx + 1}. [${ticket.status}] ${ticket.subject}\n`;
    });
    prompt += '\n';
  }
  
  prompt += `위 고객 문의에 대한 적절한 응답을 추천해주세요.`;
  
  return prompt;
}

/**
 * 추천 결과 저장 (Stub)
 * 
 * 실제 저장 로직은 후속 스프린트에서 구현 예정
 * 
 * @param suggestion - CS LLM 응답
 */
export function recordSuggestionAudit(suggestion: CsLLMResponse): void {
  // Stub 구현: 실제 저장 없이 로그만 출력
  console.log('[CS LLM Service] Suggestion audit (stub):', {
    suggestionCount: suggestion.suggestions.length,
    hasSummary: !!suggestion.summary,
    timestamp: new Date().toISOString(),
  });
}

