/**
 * OS LLM Usage 라우트
 * R10-S1: LLM Usage Audit v0
 * R10-S2: eventType 필드 처리
 *
 * @module bff-accounting/routes/os-llm-usage
 */

import { Router } from "express";
import { requireTenantAuth } from "../shared/guards.js";

export const osLlmUsageRouter = Router();

// ✅ R10-S5 P1-4: KPI 검증 상수
const MS_MIN = 0;
const MS_MAX = 600_000;
const DOC_MIN = 0;
const DOC_MAX = 10_000;
const TOPK_MIN = 1;
const TOPK_MAX = 10;

function isFiniteNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function isBool(x: unknown): x is boolean {
  return typeof x === "boolean";
}

function inRange(n: number, min: number, max: number): boolean {
  return n >= min && n <= max;
}

/**
 * ✅ R10-S5 P1-4: KPI 필드 타입/상한 검증
 * 클라이언트 실수/조작이 와도 BFF에서 "meta-only + 숫자/불리언 + 상한" 계약을 강제
 */
function validateKpi(body: any): string | null {
  const msFields = [
    "ragEmbeddingMs",
    "ragRetrieveMs",
    "ragIndexHydrateMs",
    "ragIndexBuildMs",
    "ragIndexPersistMs",
    "ragRetrieveMsP50",
    "ragRetrieveMsP95",
    "modelLoadMs",
    "inferenceMs",
    "firstByteMs",
  ];

  for (const k of msFields) {
    if (body[k] == null) continue; // undefined/null은 미전송 취급
    if (!isFiniteNumber(body[k]) || !inRange(body[k], MS_MIN, MS_MAX)) {
      return `invalid_${k}`;
    }
  }

  if (body.ragDocCount != null) {
    if (
      !isFiniteNumber(body.ragDocCount) ||
      !Number.isInteger(body.ragDocCount) ||
      !inRange(body.ragDocCount, DOC_MIN, DOC_MAX)
    ) {
      return "invalid_ragDocCount";
    }
  }

  if (body.ragTopK != null) {
    if (
      !isFiniteNumber(body.ragTopK) ||
      !Number.isInteger(body.ragTopK) ||
      !inRange(body.ragTopK, TOPK_MIN, TOPK_MAX)
    ) {
      return "invalid_ragTopK";
    }
  }

  if (body.ragIndexWarm != null && !isBool(body.ragIndexWarm)) {
    return "invalid_ragIndexWarm";
  }

  if (body.ragEnabled != null && !isBool(body.ragEnabled)) {
    return "invalid_ragEnabled";
  }

  if (body.success != null && !isBool(body.success)) {
    return "invalid_success";
  }

  if (body.fallback != null && !isBool(body.fallback)) {
    return "invalid_fallback";
  }

  if (body.cancelled != null && !isBool(body.cancelled)) {
    return "invalid_cancelled";
  }

  return null;
}

/**
 * POST /v1/os/llm-usage
 * LLM Usage 이벤트 수집
 *
 * 텍스트 원문은 받지 않고, 엔진 메타/모드/도메인/이벤트 타입 등만 수집
 */
osLlmUsageRouter.post("/", requireTenantAuth, async (req, res, next) => {
  try {
    const tenantId = (req as any).tenantId || req.body.tenantId;
    const userId = (req.headers["x-user-id"] as string) || req.body.userId;
    const userRole = (req.headers["x-user-role"] as string) || "operator";

    // P0 방화벽: 원문 텍스트 필드 차단
    // ✅ R10-S5 P0-6: RAG 원문 텍스트 필드도 차단
    const body = (req.body ?? {}) as Record<string, unknown>;
    const bannedKeys = [
      "prompt",
      "text",
      "message",
      "content",
      "responseText",
      "suggestionText",
      "raw",
      "input",
      "output",
      // RAG 원문 텍스트 필드
      "ragText",
      "ragChunk",
      "ragContext",
      "ragQuery",
      "ragResult",
      "ragSource",
      "errorMessage",
      "errorText",
      // ✅ R10-S5 P1-2: 출처/스니펫 관련 원문 텍스트 필드
      "snippet",
      "sourceSnippet",
      "excerpt",
      "subject",
      "title",
      "contextText",
      "chunkText",
      "documentText",
      "ticketBody",
      "body",
    ];

    for (const k of Object.keys(body)) {
      const lower = k.toLowerCase();
      if (bannedKeys.some((b) => lower.includes(b.toLowerCase()))) {
        return res.status(400).json({
          error: "invalid_payload",
          message: "raw text is not allowed",
        });
      }
    }

    // ✅ R10-S5 P1-4: KPI 필드 타입/상한 검증 (2차 방화벽)
    const kpiError = validateKpi(body);
    if (kpiError) {
      return res.status(400).json({
        error: kpiError,
        message: "KPI validation failed",
      });
    }

    const typedBody = body as {
      domain?: string;
      engineId?: string;
      engineVariant?: string;
      engineMode?: string;
      engineStub?: boolean;
      eventType: string; // R10-S2: 추가
      feature?: string;
      timestamp?: string;
      suggestionLength: number;
      // ✅ P0-3: 성능 메타 KPI (meta-only, 원문 금지)
      modelLoadMs?: number;
      inferenceMs?: number;
      firstByteMs?: number;
      backend?: "stub" | "real";
      success?: boolean;
      fallback?: boolean;
      cancelled?: boolean;
      // ✅ R10-S5 P0-6: RAG 메타데이터 (meta-only, 원문 금지)
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
    };

    const logEvent = {
      type: "llm_usage",
      tenant: tenantId,
      userId,
      userRole,
      ...typedBody,
      ts: new Date().toISOString(),
    };

    console.log("[QA] os-llm-usage hit", req.headers["x-request-id"] || "");
    console.log(JSON.stringify(logEvent));
    res.status(204).end();
  } catch (err) {
    next(err);
  }
});

export default osLlmUsageRouter;
