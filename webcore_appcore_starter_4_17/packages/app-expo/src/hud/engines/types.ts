/**
 * SuggestEngine 타입 정의
 * R8-S1: 온디바이스 LLM 준비를 위한 인터페이스
 * R8-S2: 엔진 모드 확장 및 메타 정보 추가
 */

export type SuggestDomain = 'accounting' | 'cs';

export type SuggestEngineMode = 'local-only' | 'remote-only' | 'hybrid';

/**
 * 엔진 모드 타입 (R8-S2)
 * EXPO_PUBLIC_ENGINE_MODE 환경 변수로 선택 가능
 * R10-S1: remote-llm 추가
 */
export type EngineMode = 'mock' | 'rule' | 'local-llm' | 'remote-llm';

/**
 * 엔진 ID 타입 (R10-S1)
 */
export type EngineId =
  | 'local-rule-v1'
  | 'local-llm'
  | 'remote-llm'
  | string; // 확장 가능성 고려

/**
 * 엔진 메타 정보 (R8-S2)
 * R10-S1: stub, variant, id, supportedDomains 필드 추가
 */
export interface SuggestEngineMeta {
  /**
   * 엔진 ID (R10-S1)
   * 예: 'local-llm', 'local-rule-v1' 등
   */
  id?: EngineId;
  /**
   * 엔진 모드
   */
  type: EngineMode;
  /**
   * 엔진 표시 레이블
   */
  label: string;
  /**
   * Stub 여부 (R10-S1)
   * true: Stub 버전 (실제 모델 미연동)
   * false: 실제 모델 연동 버전
   */
  stub?: boolean;
  /**
   * 엔진 버전/변형 (R10-S1)
   * 예: 'local-llm-v0' (Stub), 'local-llm-v1' (실제 모델), 'rule-v1' 등
   */
  variant?: string;
  /**
   * 지원 도메인 목록 (R10-S1)
   * 예: ['accounting', 'cs']
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
  source: 'local-rule' | 'remote-bff' | 'local-llm';
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
   * R10-S1: stub, variant 필드 포함
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

  /**
   * 엔진 메타 정보 조회 (R10-S1)
   * HUD 상태바, OS Dashboard, 로그 등에서 사용
   */
  getMeta(): SuggestEngineMeta;

  canHandleDomain(domain: SuggestDomain): boolean;

  suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>>;
}

