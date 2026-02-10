/**
 * P1-PLAT-01: Trace HTTP Routes v1
 * 목적: POST /v1/trace 엔드포인트
 * - 로컬-only 또는 인증 필수 (0.0.0.0 금지)
 * - X-Api-Key 값 매칭 (존재만 금지)
 * - IPv6/::ffff: 포함
 */

import express from "express";
import type { Request, Response } from "express";
import type { TraceStore } from "../../store/db/sqljs_store";
import { ReasonCodeV1 } from "../../../../../common/src/reason_codes/reason_codes_v1";

const ALLOWED_API_KEY = process.env.TRACE_API_KEY || "test-key-change-in-prod";

/**
 * 접근 잠금: 로컬-only 또는 인증 필수
 * IPv6/::ffff: 포함
 */
function checkAccess(req: Request): { allowed: boolean; reason?: string } {
  // 1) X-Api-Key 값 매칭 (존재만 금지)
  const apiKey = req.headers["x-api-key"];
  if (apiKey && typeof apiKey === "string" && apiKey === ALLOWED_API_KEY) {
    return { allowed: true };
  }

  // 2) 로컬-only 확인 (IPv4/IPv6 포함)
  const ip = req.ip || req.socket.remoteAddress || "";
  const normalizedIp = ip.replace(/^::ffff:/, ""); // IPv6-mapped IPv4
  
  // 빈 IP는 fail-closed (거부)
  if (!normalizedIp || normalizedIp === "") {
    return { allowed: false, reason: ReasonCodeV1.ACCESS_DENIED };
  }
  
  if (
    normalizedIp === "127.0.0.1" ||
    normalizedIp === "::1" ||
    normalizedIp === "localhost"
  ) {
    return { allowed: true };
  }

  // 3) 0.0.0.0 바인딩 통과 금지
  if (normalizedIp === "0.0.0.0" || normalizedIp === "::") {
    return { allowed: false, reason: ReasonCodeV1.ACCESS_DENIED };
  }

  return { allowed: false, reason: ReasonCodeV1.ACCESS_DENIED };
}

export function buildTraceRouter(store: TraceStore) {
  const r = express.Router();
  r.use(express.json({ limit: "32kb" }));

  r.post("/v1/trace", async (req: Request, res: Response) => {
    try {
      // 접근 잠금 확인
      const access = checkAccess(req);
      if (!access.allowed) {
        // 실패 응답에 원문/세부 내용 포함 금지
        return res.status(403).json({
          ok: false,
          error_code: access.reason || "ACCESS_DENIED",
        });
      }

      // ingest (저장 전 검증은 store.ingest 내부에서 수행)
      const result = await store.ingest(req.body);
      
      res.json({
        ok: true,
        inserted: result.inserted,
      });
    } catch (e: any) {
      // 실패 응답에 원문/세부 내용 포함 금지
      const errorCode = e?.message || "INGEST_FAILED";
      res.status(400).json({
        ok: false,
        error_code: errorCode,
      });
    }
  });

  return r;
}

