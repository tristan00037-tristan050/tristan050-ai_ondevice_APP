import { bffUrl } from "../bff";
import { buildTenantHeaders, type TenantHeadersInput } from "../tenantHeaders";
import type { OsLlmUsageEventType } from "./eventTypes";
import { validateTelemetryPayload } from "./metaOnlyGuard";

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
  // ✅ R10-S5 P0-6: RAG 메타데이터 (meta-only, 원문 금지)
  ragEnabled?: boolean;
  ragDocs?: number; // 검색된 문서 수 (0~10)
  ragTopK?: number; // 검색 상위 K개 (1~10)
  ragContextChars?: number; // 주입한 컨텍스트 문자 수 (0~20000)
  ragEmbeddingMs?: number; // 임베딩 소요 시간 (ms, 0~600000)
  ragRetrieveMs?: number; // 검색 소요 시간 (ms, 0~600000)
  ragIndexWarm?: boolean; // 인덱스 Warm start 여부
  ragIndexBuildMs?: number; // 인덱스 빌드 소요 시간 (ms, 0~600000)
  ragIndexPersistMs?: number; // 인덱스 영속화 소요 시간 (ms, 0~600000)
  ragIndexHydrateMs?: number; // 인덱스 복원 소요 시간 (ms, 0~600000)
  ragDocCount?: number; // 인덱스에 저장된 문서 수 (0~10000)
  // ✅ R10-S5 P1-4: 성능 KPI 분포 지표 (p50/p95)
  ragRetrieveMsP50?: number; // 검색 소요 시간 p50 (ms, 0~600000)
  ragRetrieveMsP95?: number; // 검색 소요 시간 p95 (ms, 0~600000)
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
  // ✅ R10-S5 P0-6: RAG 메타데이터 (optional, meta-only)
  ragEnabled?: boolean;
  ragDocs?: number;
  ragTopK?: number;
  ragContextChars?: number;
  ragEmbeddingMs?: number;
  ragRetrieveMs?: number;
  ragIndexWarm?: boolean;
  ragIndexBuildMs?: number;
  ragIndexPersistMs?: number;
  ragIndexHydrateMs?: number;
  ragDocCount?: number;
  // ✅ R10-S5 P1-4: 성능 KPI 분포 지표 (p50/p95)
  ragRetrieveMsP50?: number;
  ragRetrieveMsP95?: number;
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

  // ✅ P0-H + P0-3 + R10-S5 P0-6: Payload 필터링 (원문 키 차단, 성능/RAG 메타만 허용)
  // 허용된 필드만 추출하여 전송 (원문 텍스트 필드 절대 금지)
  // 타입 체크: 숫자/불리언/enum만 허용, 문자열은 고정 enum만 허용 (자유 텍스트 금지)
  
  // ✅ R10-S5 P0-6: 상한/정규화 헬퍼
  const clampNumber = (value: number, min: number, max: number): number => {
    if (!Number.isFinite(value)) return 0;
    return Math.max(min, Math.min(max, Math.trunc(value)));
  };
  
  const clampTimeMs = (value: number | undefined): number | undefined => {
    if (value === undefined) return undefined;
    const clamped = clampNumber(value, 0, 600000); // 10분 상한
    return clamped > 0 ? clamped : undefined;
  };

  const payload: OsLlmUsageEvent = {
    eventType: evt.eventType,
    suggestionLength: clampNumber(evt.suggestionLength, 0, 1000000), // 100만자 상한
    // 성능 메타 (optional, 숫자/불리언만)
    ...(Number.isFinite(evt.modelLoadMs) && { modelLoadMs: clampTimeMs(evt.modelLoadMs) }),
    ...(Number.isFinite(evt.inferenceMs) && { inferenceMs: clampTimeMs(evt.inferenceMs) }),
    ...(Number.isFinite(evt.firstByteMs) && { firstByteMs: clampTimeMs(evt.firstByteMs) }),
    ...(evt.backend === "stub" || evt.backend === "real" ? { backend: evt.backend } : {}),
    ...(typeof evt.success === "boolean" ? { success: evt.success } : {}),
    ...(typeof evt.fallback === "boolean" ? { fallback: evt.fallback } : {}),
    ...(typeof evt.cancelled === "boolean" ? { cancelled: evt.cancelled } : {}),
    // ✅ R10-S5 P0-6: RAG 메타 (optional, 타입 체크 + 상한 적용)
    ...(typeof evt.ragEnabled === "boolean" ? { ragEnabled: evt.ragEnabled } : {}),
    ...(Number.isFinite(evt.ragDocs) && { ragDocs: clampNumber(evt.ragDocs, 0, 10) }),
    ...(Number.isFinite(evt.ragTopK) && { ragTopK: clampNumber(evt.ragTopK, 1, 10) }),
    ...(Number.isFinite(evt.ragContextChars) && { ragContextChars: clampNumber(evt.ragContextChars, 0, 20000) }),
    ...(Number.isFinite(evt.ragEmbeddingMs) && { ragEmbeddingMs: clampTimeMs(evt.ragEmbeddingMs) }),
    ...(Number.isFinite(evt.ragRetrieveMs) && { ragRetrieveMs: clampTimeMs(evt.ragRetrieveMs) }),
    ...(typeof evt.ragIndexWarm === "boolean" ? { ragIndexWarm: evt.ragIndexWarm } : {}),
    ...(Number.isFinite(evt.ragIndexBuildMs) && { ragIndexBuildMs: clampTimeMs(evt.ragIndexBuildMs) }),
    ...(Number.isFinite(evt.ragIndexPersistMs) && { ragIndexPersistMs: clampTimeMs(evt.ragIndexPersistMs) }),
    ...(Number.isFinite(evt.ragIndexHydrateMs) && { ragIndexHydrateMs: clampTimeMs(evt.ragIndexHydrateMs) }),
    ...(Number.isFinite(evt.ragDocCount) && { ragDocCount: clampNumber(evt.ragDocCount, 0, 10000) }),
    // ✅ R10-S5 P1-4: 성능 KPI 분포 지표 (p50/p95)
    ...(Number.isFinite(evt.ragRetrieveMsP50) && { ragRetrieveMsP50: clampTimeMs(evt.ragRetrieveMsP50) }),
    ...(Number.isFinite(evt.ragRetrieveMsP95) && { ragRetrieveMsP95: clampTimeMs(evt.ragRetrieveMsP95) }),
  };

  // ✅ APP-04: SDK-side meta-only guard (fail-closed)
  // 전송 전 검증: identifier/raw-text/candidate-list 차단
  const validation = validateTelemetryPayload(payload);
  if (!validation.valid) {
    // Fail-Closed: 전송하지 않고 reason_code만 로깅
    console.warn(
      "[osTelemetry] BLOCKED: meta-only validation failed",
      validation.reason_code,
      validation.message
    );
    return; // 전송하지 않음
  }

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
