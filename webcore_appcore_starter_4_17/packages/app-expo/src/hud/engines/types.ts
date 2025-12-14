/**
 * SuggestEngine 타입 정의
 * R8-S1: 온디바이스 LLM 준비를 위한 인터페이스
 * R8-S2: 엔진 모드 확장 및 메타 정보 추가
 */

export type SuggestDomain = "accounting" | "cs";

export type SuggestEngineMode = "local-only" | "remote-only" | "hybrid";

/**
 * 엔진 모드 타입 (R8-S2)
 * EXPO_PUBLIC_ENGINE_MODE 환경 변수로 선택 가능
 */
export type EngineMode = "mock" | "rule" | "local-llm" | "remote";

/**
 * 엔진 메타 정보 (R8-S2)
 * R10-S3: variant, stub 필드 추가 (E06-1)
 */
export interface SuggestEngineMeta {
  type: EngineMode;
  label: string;
  /**
   * 엔진 variant (예: 'local-llm-v0', 'local-llm-v1')
   * R10-S3: 실제 모델 버전 구분용
   */
  variant?: string;
  /**
   * Stub 여부 (true: 더미/시뮬레이션, false: 실제 모델)
   * R10-S3: 실제 모델 vs Stub 구분용
   */
  stub?: boolean;
  /**
   * 지원 도메인 목록
   * R10-S2: 도메인별 지원 여부 명시
   */
  supportedDomains?: SuggestDomain[];
}

export interface SuggestContext {
  domain: SuggestDomain;
  tenantId: string;
  userId: string;
  locale?: string;
}

export interface SuggestInput {
  text: string;
  meta?: Record<string, unknown>;
}

export interface SuggestItem<TPayload = unknown> {
  id: string;
  title: string;
  description?: string;
  score?: number;
  payload?: TPayload;
  source: "local-rule" | "remote-bff" | "local-llm";
}

export interface SuggestResult<TPayload = unknown> {
  items: SuggestItem<TPayload>[];
  engine: string;
  confidence?: number;
}

export interface SuggestEngine {
  readonly id: string;
  readonly mode: SuggestEngineMode;

  /**
   * 엔진 메타 정보 (R8-S2)
   */
  meta: SuggestEngineMeta;

  /**
   * 엔진 초기화 상태 (R8-S2)
   */
  isReady: boolean;

  /**
   * 엔진 초기화 메서드 (선택적, R8-S2)
   */
  initialize?(): Promise<void>;

  canHandleDomain(domain: SuggestDomain): boolean;

  suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput
  ): Promise<SuggestResult<TPayload>>;
}

// ============================================================================
// CS LLM용 타입 정의 (R9-S2)
// ============================================================================

/**
 * CS LLM용 공통 Role 타입
 */
export type CsLLMRole = "user" | "agent" | "system";

/**
 * CS LLM 히스토리 한 줄
 */
export interface CsLLMHistoryItem {
  role: CsLLMRole;
  content: string;
}

/**
 * CS LLM 컨텍스트 (티켓 + 히스토리)
 */
export interface CsLLMContext {
  tenantId: string;
  ticketId: string;
  subject: string;
  body: string;
  history: CsLLMHistoryItem[];
}

/**
 * 엔진이 반환하는 CS 응답 한 건
 */
export interface CsResponseSuggestion {
  id: string;
  replyText: string;
  createdAt: string; // ISO string
  source: "rule" | "local-llm" | "remote-llm";
}

/**
 * 엔진이 반환하는 전체 CS LLM 결과
 */
export interface CsLLMResponse {
  summary?: string;
  suggestions: CsResponseSuggestion[];
}

/**
 * SuggestEngine에서 사용할 CS 도메인 컨텍스트
 * (기존 accounting 쪽 컨텍스트와 나란히 두고 union으로 묶을 수 있습니다)
 */
export interface CsSuggestContext {
  domain: "cs";
  tenantId: string;
  ticket: {
    id: string;
    subject: string;
    body: string;
    status: string;
    createdAt: string; // CsHUD에서 넘기는 createdAt과 맞춤
  };
  // 필요 시 LLM 컨텍스트 전체를 붙이고 싶을 때 사용
  llmContext?: CsLLMContext;
}
