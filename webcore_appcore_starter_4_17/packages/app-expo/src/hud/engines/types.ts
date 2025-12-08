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
 */
export type EngineMode = 'mock' | 'rule' | 'local-llm' | 'remote';

/**
 * 엔진 메타 정보 (R8-S2)
 */
export interface SuggestEngineMeta {
  type: EngineMode;
  label: string;
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
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>>;
}

