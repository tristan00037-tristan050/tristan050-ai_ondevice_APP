/**
 * HUD 레벨 LLM 응답 후처리 유틸
 * R10-S2: 공통 텍스트 후처리 (정규화, 길이 제한, 추후 PII 필터 자리)
 * 
 * @module app-expo/hud/engines/llmPostProcess
 */

import type { SuggestEngineMeta, EngineMode, SuggestDomain } from './types';

export interface LlmPostProcessContext {
  domain: SuggestDomain;
  engineMeta: SuggestEngineMeta;
  mode: EngineMode;
}

/**
 * HUD 레벨 LLM 응답 후처리:
 * - 개행/공백 정리
 * - 길이 제한
 * - (훗날) 클라이언트 측 PII/금지 표현 필터 자리
 * 
 * @param ctx - 후처리 컨텍스트
 * @param text - 원본 텍스트
 * @returns 후처리된 텍스트
 */
export function applyLlmTextPostProcess(
  ctx: LlmPostProcessContext,
  text: string,
): string {
  if (!text) return text;

  let out = text;

  // 1) 개행 정리
  out = out.replace(/\r\n/g, '\n');

  // 2) 앞뒤 공백 제거
  out = out.trim();

  // 3) 지나치게 긴 응답은 UI 보호를 위해 잘라낸 뒤 태그 추가
  const MAX_LEN = 4000;
  if (out.length > MAX_LEN) {
    out =
      out.slice(0, MAX_LEN) +
      '\n\n[HUD post-processor: response truncated for display]';
  }

  // 4) (TODO) 민감 정보/금지 표현 필터 훅
  // 예: 전화번호/이메일/주민번호 패턴 탐지 후 마스킹
  // out = maskSensitive(out);

  return out;
}

