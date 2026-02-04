/**
 * LLM Usage Telemetry
 * R10-S1: LLM Usage Audit v0
 * R10-S2: eventType 추가
 *
 * @module app-expo/hud/telemetry/llmUsage
 */

import { mkHeaders } from '../accounting-api';
import type { ClientCfg } from '../accounting-api';
import type {
  EngineMode,
  SuggestDomain,
  SuggestEngineMeta,
} from '../engines/types';
import type { SuggestEngine } from '../engines/types';
import { validateTelemetryPayload } from '../../os/telemetry/metaOnlyGuard';

/**
 * LLM Usage 이벤트 타입
 * R10-S2: Manual Touch Rate, 추천 사용률, 수정률, 거부률 측정을 위한 세분화
 */
export type LlmUsageEventType =
  | 'shown' // 추천 패널 표시
  | 'accepted_as_is' // 그대로 사용
  | 'edited' // 수정 후 전송
  | 'rejected' // 추천 닫기/무시
  | 'error'; // 엔진 에러

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
  eventType: LlmUsageEventType; // R10-S2: 추가
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
  // R10-S3: EngineMeta 확장(variant, stub) 반영 (E06-1)
  const payload: LlmUsageEvent = {
    ...evt,
    engineId: engine.id || 'unknown',
    engineVariant: engine.meta.variant,
    engineMode: engine.meta.type,
    engineStub: engine.meta.stub ?? (engine.meta.type === 'local-llm'), // 기본값: local-llm은 Stub로 간주
  };

  if (cfg.mode === 'mock') {
    console.log('[MOCK] LLM usage event', payload);
    return;
  }

  // ✅ APP-04: SDK-side meta-only guard (fail-closed)
  // 전송 전 검증: identifier/raw-text/candidate-list 차단
  const validation = validateTelemetryPayload(payload);
  if (!validation.valid) {
    // Fail-Closed: 전송하지 않고 reason_code만 로깅
    console.warn(
      '[llmUsage] BLOCKED: meta-only validation failed',
      validation.reason_code,
      validation.message
    );
    return; // 전송하지 않음
  }

  await fetch(`${cfg.baseUrl}/v1/os/llm-usage`, {
    method: 'POST',
    headers: mkHeaders(cfg),
    body: JSON.stringify(payload),
  });
}
