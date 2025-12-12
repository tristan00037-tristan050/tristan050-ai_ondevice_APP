/**
 * OS 공통 LLM 서비스 인터페이스
 * R10-S2: 모든 도메인(service-core-*)이 이 규격을 구현해야 함
 * 
 * @module service-core-common/llm/domainLLMService
 */

/**
 * Domain LLM Service 공통 인터페이스
 * 
 * 회계/CS/HR/법무/보안 등 모든 도메인이 이 인터페이스를 구현하여
 * LLM 호출·프롬프트·감사 패턴을 OS 레벨에서 표준화
 * 
 * @template TContext - 도메인별 LLM 컨텍스트 타입
 * @template TResponse - 도메인별 LLM 응답 타입
 */
export interface DomainLLMService<TContext, TResponse> {
  /**
   * 도메인별 LLM 컨텍스트 구성
   * 예: 티켓/사용자/이력 등 수집
   * 
   * @param args - 도메인별 컨텍스트 구성에 필요한 인자들
   * @returns LLM 컨텍스트 (동기 또는 비동기)
   */
  buildContext(...args: any[]): Promise<TContext> | TContext;

  /**
   * LLM에 보낼 프롬프트 문자열 생성
   * 
   * @param ctx - buildContext로 구성된 LLM 컨텍스트
   * @returns LLM 프롬프트 문자열
   */
  buildPrompt(ctx: TContext): string;

  /**
   * LLM 응답을 감사 로그/사용량 등에 기록
   * 
   * @param ctx - LLM 컨텍스트
   * @param res - LLM 응답
   */
  recordAudit(ctx: TContext, res: TResponse): Promise<void>;

  /**
   * (선택) 응답 후처리 훅
   * - 개인정보 마스킹, 금지 표현 제거 등
   * - R10-S2/P1에서 실제 로직 채워질 예정
   * 
   * @param ctx - LLM 컨텍스트
   * @param res - 원본 LLM 응답
   * @returns 후처리된 LLM 응답 (동기 또는 비동기)
   */
  postProcess?(ctx: TContext, res: TResponse): Promise<TResponse> | TResponse;
}

