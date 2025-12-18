import { bffUrl } from "../bff";
import { buildTenantHeaders, type TenantHeadersInput } from "../tenantHeaders";

export type DemoMode = "mock" | "live";

export type OsLlmUsageEvent = {
  eventType: string;
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
  evt: OsLlmUsageEvent
): Promise<void> {
  // DEMO_MODE=mock => Network 0 보장
  if (demoMode === "mock") {
    console.log("[osTelemetry] Mock mode: skipping network request");
    return;
  }

  // Payload allowlist: eventType + suggestionLength only (원문 텍스트 금지)
  const payload: OsLlmUsageEvent = {
    eventType: evt.eventType,
    suggestionLength: evt.suggestionLength,
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
