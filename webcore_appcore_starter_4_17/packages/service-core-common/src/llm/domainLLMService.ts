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
   * (선택) LLM이 반환한 응답을 도메인/OS 정책에 맞게 후처리하는 훅
   * 
   * - 예: 공백/포맷 정리
   * - 예: 민감 정보(전화번호/주민번호 등) 마스킹
   * - 예: 금지 표현/부적절 응답 필터링
   * 
   * 구현하지 않으면 raw 응답이 그대로 사용된다.
   * 
   * @param ctx - LLM 컨텍스트
   * @param raw - 원본 LLM 응답
   * @returns 후처리된 LLM 응답 (동기 또는 비동기)
   */
  postProcess?(
    ctx: TContext,
    raw: TResponse,
  ): Promise<TResponse> | TResponse;
}

