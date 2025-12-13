/**
 * LLM Usage Telemetry
 * R10-S1: LLM Usage Audit v0
 * R10-S2: eventType 추가
 * 
 * @module app-expo/hud/telemetry/llmUsage
 */

import { mkHeaders } from '../accounting-api';
import type { ClientCfg } from '../accounting-api';
import type { EngineMode, SuggestDomain, SuggestEngineMeta } from '../engines/types';
import type { SuggestEngine } from '../engines/types';

/**
 * LLM Usage 이벤트 타입
 * R10-S2: Manual Touch Rate, 추천 사용률, 수정률, 거부률 측정을 위한 세분화
 */
export type LlmUsageEventType =
  | 'shown'              // 추천 패널 표시
  | 'accepted_as_is'    // 그대로 사용
  | 'edited'             // 수정 후 전송
  | 'rejected'           // 추천 닫기/무시
  | 'error';             // 엔진 에러

/**
 * LLM Usage 이벤트
 * R10-S2: eventType 필드 추가
 */
export interface LlmUsageEvent {
  tenantId: string;
  userId: string;
  domain: SuggestDomain;
  engineId: string;
  engineVariant?: string;
  engineMode: EngineMode;
  engineStub?: boolean;
  eventType: LlmUsageEventType;  // R10-S2: 추가
  feature: string;
  timestamp: string;
  suggestionLength: number;
}

/**
 * LLM Usage 이벤트 전송
 * 
 * @param cfg - 클라이언트 설정
 * @param engine - SuggestEngine 인스턴스
 * @param evt - 이벤트 데이터 (engineId, engineVariant, engineMode, engineStub 제외)
 */
export async function sendLlmUsageEvent(
  cfg: ClientCfg,
  engine: SuggestEngine,
  evt: Omit<LlmUsageEvent, 'engineId' | 'engineVariant' | 'engineMode' | 'engineStub'>,
) {
  // R10-S2: engine.id와 engine.meta를 사용하여 메타 정보 구성
  // TODO: R10-S1의 EngineMeta 확장(id, stub, variant, supportedDomains)이 반영되면 수정
  const payload: LlmUsageEvent = {
    ...evt,
    engineId: engine.id || 'unknown',
    engineVariant: undefined, // TODO: EngineMeta 확장 후 meta.variant 사용
    engineMode: engine.meta.type,
    engineStub: engine.meta.type === 'local-llm', // local-llm은 현재 Stub
  };

  if (cfg.mode === 'mock') {
    console.log('[MOCK] LLM usage event', payload);
    return;
  }

  await fetch(`${cfg.baseUrl}/v1/os/llm-usage`, {
    method: 'POST',
    headers: mkHeaders(cfg),
    body: JSON.stringify(payload),
  });
}

