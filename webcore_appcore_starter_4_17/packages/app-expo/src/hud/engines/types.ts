/**
 * SuggestEngine 타입 정의
 * R8-S1: 온디바이스 LLM 준비를 위한 인터페이스
 */

export type SuggestDomain = 'accounting' | 'cs';

export type SuggestEngineMode = 'local-only' | 'remote-only' | 'hybrid';

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

  canHandleDomain(domain: SuggestDomain): boolean;

  suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<TPayload>>;
}

