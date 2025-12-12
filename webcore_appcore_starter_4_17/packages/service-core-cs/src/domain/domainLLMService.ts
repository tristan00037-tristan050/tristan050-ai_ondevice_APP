/**
 * Domain LLM Service 공통 인터페이스
 * R10-S1: 회계/CS/HR/법무/보안 등이 같은 LLM 패턴을 공유하도록 추상화
 * 
 * @module service-core-cs/domain/domainLLMService
 */

/**
 * Domain LLM Service 인터페이스
 * 
 * 모든 도메인(회계, CS, HR, 법무, 보안 등)의 LLM 서비스가 구현해야 하는 공통 인터페이스
 * 
 * @template TContext - 도메인별 LLM 컨텍스트 타입
 * @template TResponse - 도메인별 LLM 응답 타입
 */
export interface DomainLLMService<TContext, TResponse> {
  /**
   * LLM 컨텍스트 구성
   * 
   * @param args - 도메인별 인자 (예: ticket, history 등)
   * @returns LLM 컨텍스트
   */
  buildContext(...args: any[]): Promise<TContext> | TContext;

  /**
   * LLM 프롬프트 생성
   * 
   * @param ctx - LLM 컨텍스트
   * @returns 프롬프트 문자열
   */
  buildPrompt(ctx: TContext): string;

  /**
   * LLM 사용 감사(Audit) 기록
   * 
   * @param ctx - LLM 컨텍스트
   * @param res - LLM 응답
   * @returns Promise<void>
   */
  recordAudit(ctx: TContext, res: TResponse): Promise<void>;
}

