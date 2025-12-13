/**
 * OS LLM Gateway 타입 정의
 * R10-S2: Remote LLM Gateway 설계
 * 
 * @module bff-accounting/routes/os-llm-gateway.types
 */

/**
 * LLM Gateway 작업 타입
 */
export type LlmGatewayTaskType =
  | 'suggest'     // 제안/추천 (CS 답변, 회계 분개 등)
  | 'summarize'   // 요약
  | 'classify'    // 분류
  | 'freeform';   // 그 외 (필요시 확장)

/**
 * LLM Gateway 요청 바디
 * 
 * ⚠️ 텍스트 원문: 실제로는 "이미 사내 정책 상 외부 전송 허용된 텍스트"만 들어와야 함.
 */
export interface LlmGatewayRequestBody {
  domain: 'accounting' | 'cs' | string; // SuggestDomain과 매핑 예정
  taskType: LlmGatewayTaskType;

  engineId: string;      // 예: 'remote-llm'
  engineVariant?: string; // 예: 'remote-llm-v1'

  // ⚠️ 텍스트 원문: 실제로는 "이미 사내 정책 상 외부 전송 허용된 텍스트"만 들어와야 함.
  prompt: string;

  maxTokens?: number;
  temperature?: number;

  // 추후 KPI/추적용 메타
  traceId?: string;
  hudDomain?: string; // 'cs-ticket-hud', 'acct-posting-hud' 등
}

/**
 * LLM Gateway 응답 바디
 * 
 * 현 단계는 단일 텍스트; 나중에 토큰 스트리밍/structured로 확장
 */
export interface LlmGatewayResponseBody {
  id: string; // gateway-side 요청 id
  engineId: string;
  engineVariant?: string;
  createdAt: string; // ISO

  output: string; // 현 단계는 단일 텍스트; 나중에 토큰 스트리밍/structured로 확장

  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };

  // 추후 분석/디버깅용
  traceId?: string;
}

