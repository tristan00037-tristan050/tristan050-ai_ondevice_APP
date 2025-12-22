import { bffUrl } from "../bff";
import { buildTenantHeaders, type TenantHeadersInput } from "../tenantHeaders";
import type { OsLlmUsageEventType } from "./eventTypes";

export type DemoMode = "mock" | "live";

export type OsLlmUsageEvent = {
  eventType: OsLlmUsageEventType;
  suggestionLength: number;
  // ✅ P0-3: 성능 측정 표준 메타 KPI (meta-only, 원문 금지)
  modelLoadMs?: number; // 모델 로딩 소요 시간 (ms)
  inferenceMs?: number; // 추론 소요 시간 (ms)
  firstByteMs?: number; // 첫 토큰까지 소요 시간 (ms, 스트리밍 시)
  backend?: "stub" | "real"; // 백엔드 타입
  success?: boolean; // 성공 여부
  fallback?: boolean; // stub fallback 사용 여부
  cancelled?: boolean; // 사용자 취소 여부
};

/**
 * OS 공통 LLM Usage Telemetry
 * - Mock 모드: Network 0 보장 (NO-OP)
 * - Live 모드: BFF로 전송
 * - Payload: eventType + suggestionLength만 (원문 텍스트 금지)
 */
export interface LlmUsageEventInput {
  eventType: OsLlmUsageEventType;
  suggestionLength: number;
  // ✅ P0-3: 성능 메타 (optional)
  modelLoadMs?: number;
  inferenceMs?: number;
  firstByteMs?: number;
  backend?: "stub" | "real";
  success?: boolean;
  fallback?: boolean;
  cancelled?: boolean;
}

export async function recordLlmUsage(
  demoMode: DemoMode,
  auth: TenantHeadersInput,
  evt: LlmUsageEventInput
): Promise<void> {
  // DEMO_MODE=mock => Network 0 보장
  if (demoMode === "mock") {
    console.log("[osTelemetry] Mock mode: skipping network request");
    return;
  }

  // ✅ P0-H + P0-3: Payload 필터링 (원문 키 차단, 성능 메타만 허용)
  // 허용된 필드만 추출하여 전송 (원문 텍스트 필드 절대 금지)
  const payload: OsLlmUsageEvent = {
    eventType: evt.eventType,
    suggestionLength: Number.isFinite(evt.suggestionLength)
      ? Math.max(0, Math.trunc(evt.suggestionLength))
      : 0,
    // 성능 메타 (optional, 숫자/불리언만)
    ...(Number.isFinite(evt.modelLoadMs) && { modelLoadMs: Math.max(0, Math.trunc(evt.modelLoadMs!)) }),
    ...(Number.isFinite(evt.inferenceMs) && { inferenceMs: Math.max(0, Math.trunc(evt.inferenceMs!)) }),
    ...(Number.isFinite(evt.firstByteMs) && { firstByteMs: Math.max(0, Math.trunc(evt.firstByteMs!)) }),
    ...(evt.backend === "stub" || evt.backend === "real" ? { backend: evt.backend } : {}),
    ...(typeof evt.success === "boolean" ? { success: evt.success } : {}),
    ...(typeof evt.fallback === "boolean" ? { fallback: evt.fallback } : {}),
    ...(typeof evt.cancelled === "boolean" ? { cancelled: evt.cancelled } : {}),
  };

  const url = bffUrl("/v1/os/llm-usage");
  const headers = {
    "Content-Type": "application/json",
    ...buildTenantHeaders(auth),
  };

  console.log("[osTelemetry] Sending POST to", url);
  console.log("[osTelemetry] Headers:", headers);
  console.log("[osTelemetry] Payload:", payload);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    console.log(
      "[osTelemetry] Response status:",
      response.status,
      response.statusText
    );
    if (!response.ok) {
      const text = await response.text();
      console.warn("[osTelemetry] Response error:", text);
    }
  } catch (error) {
    console.error("[osTelemetry] Fetch failed:", error);
    throw error;
  }
}
