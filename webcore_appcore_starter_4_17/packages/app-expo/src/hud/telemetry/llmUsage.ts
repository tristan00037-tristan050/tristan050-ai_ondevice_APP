/**
 * LLM Usage Telemetry
 * R10-S1: LLM 사용 감사(Audit) 이벤트 전송 유틸
 * 
 * @module app-expo/hud/telemetry/llmUsage
 */

import { mkHeaders } from '../accounting-api';
import type { ClientCfg } from '../accounting-api';
import type { EngineMode, EngineMeta, SuggestDomain } from '../engines/types';

/**
 * LLM 추천 결과 타입
 */
export type LlmSuggestionOutcome =
  | 'shown'        // 추천이 화면에 표시됨
  | 'used_as_is'  // 그대로 적용됨
  | 'edited'       // 수정 후 전송됨
  | 'rejected'     // 무시됨
  | 'error';       // 에러 발생

/**
 * LLM 사용 이벤트
 * 
 * Playbook 규칙에 따라 원문 텍스트는 수집하지 않고,
 * 메타데이터(길이, 엔진 모드, 도메인 등)만 수집
 * R10-S1: 엔진 메타 정보 포함
 */
export interface LlmUsageEvent {
  tenantId: string;
  userId: string;
  domain: SuggestDomain;
  engineId: string;
  engineVariant?: string;
  engineMode: EngineMode;
  engineStub?: boolean;
  outcome: LlmSuggestionOutcome;
  feature: string;      // 예: 'cs_reply_suggest'
  timestamp: string;
  suggestionLength: number;
  // 텍스트 전문은 절대 보내지 않음 (Playbook 규칙)
}

/**
 * LLM 사용 이벤트 전송
 * 
 * @param cfg - 클라이언트 설정
 * @param meta - 엔진 메타 정보
 * @param evt - LLM 사용 이벤트 (엔진 메타 제외)
 * @returns Promise<void>
 */
export async function sendLlmUsageEvent(
  cfg: ClientCfg,
  meta: EngineMeta,
  evt: Omit<LlmUsageEvent, 'engineId' | 'engineVariant' | 'engineMode' | 'engineStub'>,
): Promise<void> {
  const payload: LlmUsageEvent = {
    ...evt,
    engineId: meta.id || 'unknown',
    engineVariant: meta.variant,
    engineMode: meta.type,
    engineStub: meta.stub,
  };

  // Mock 모드: 네트워크 요청 없이 로그만 기록
  if (cfg.mode === 'mock') {
    console.log('[MOCK] LLM usage event', payload);
    return;
  }

  // Live 모드: BFF로 이벤트 전송
  try {
    const response = await fetch(`${cfg.baseUrl}/v1/os/llm-usage`, {
      method: 'POST',
      headers: mkHeaders(cfg, {
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error('[LLM Usage] Failed to send event:', response.status, response.statusText);
    }
  } catch (error) {
    console.error('[LLM Usage] Error sending event:', error);
    // 에러가 발생해도 앱 동작에는 영향 없음 (감사 로그이므로)
  }
}

