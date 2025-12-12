/**
 * 도메인 핸들러 레지스트리
 * R10-S1: 엔진 if/switch 폭발 방지를 위한 도메인 핸들러 패턴 준비
 * 
 * @module app-expo/hud/engines/domainHandlers
 */

import type {
  SuggestContext,
  SuggestInput,
  SuggestResult,
  SuggestDomain,
} from './types';

/**
 * 도메인 핸들러 인터페이스
 * 
 * 각 도메인(accounting, cs, hr, legal, security 등)의 LLM 추천 로직을 캡슐화
 */
export interface DomainHandler {
  /**
   * 도메인 식별자
   */
  domain: SuggestDomain;

  /**
   * 도메인별 추천 생성
   * 
   * @param ctx - Suggest 컨텍스트
   * @param input - Suggest 입력
   * @returns Suggest 결과
   */
  suggest(
    ctx: SuggestContext,
    input: SuggestInput,
  ): Promise<SuggestResult<any>>;
}

/**
 * 도메인 핸들러 레지스트리
 * 
 * 도메인별 핸들러를 등록하고 조회할 수 있는 맵
 */
const handlers = new Map<SuggestDomain, DomainHandler>();

/**
 * 도메인 핸들러 등록
 * 
 * @param handler - 도메인 핸들러
 */
export function registerDomainHandler(handler: DomainHandler): void {
  handlers.set(handler.domain, handler);
  console.log(`[DomainHandlers] Registered handler for domain: ${handler.domain}`);
}

/**
 * 도메인 핸들러 조회
 * 
 * @param domain - 도메인 식별자
 * @returns 도메인 핸들러 또는 undefined
 */
export function getDomainHandler(domain: SuggestDomain): DomainHandler | undefined {
  return handlers.get(domain);
}

/**
 * 등록된 모든 도메인 목록 조회
 * 
 * @returns 등록된 도메인 목록
 */
export function getRegisteredDomains(): SuggestDomain[] {
  return Array.from(handlers.keys());
}

