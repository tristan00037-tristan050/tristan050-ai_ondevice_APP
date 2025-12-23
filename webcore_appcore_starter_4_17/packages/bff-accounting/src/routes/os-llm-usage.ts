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
