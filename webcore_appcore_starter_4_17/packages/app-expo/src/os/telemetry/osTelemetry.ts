import { bffUrl } from "../bff";
import { buildTenantHeaders, type TenantHeadersInput } from "../tenantHeaders";
import type { OsLlmUsageEventType } from "./eventTypes";

export type DemoMode = "mock" | "live";

export type OsLlmUsageEvent = {
  eventType: OsLlmUsageEventType;
  suggestionLength: number;
};

/**
 * OS 공통 LLM Usage Telemetry
 * - Mock 모드: Network 0 보장 (NO-OP)
 * - Live 모드: BFF로 전송
 * - Payload: eventType + suggestionLength만 (원문 텍스트 금지)
 */
export async function recordLlmUsage(
  demoMode: DemoMode,
  auth: TenantHeadersInput,
  evt: { eventType: OsLlmUsageEventType; suggestionLength: number }
): Promise<void> {
  // DEMO_MODE=mock => Network 0 보장
  if (demoMode === "mock") {
    console.log("[osTelemetry] Mock mode: skipping network request");
    return;
  }

  // ✅ P0-H: Payload를 2필드로 강제 (원문 키가 실수로 들어와도 전송 자체를 차단)
  const payload: OsLlmUsageEvent = {
    eventType: evt.eventType,
    suggestionLength: Number.isFinite(evt.suggestionLength)
      ? Math.max(0, Math.trunc(evt.suggestionLength))
      : 0,
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
