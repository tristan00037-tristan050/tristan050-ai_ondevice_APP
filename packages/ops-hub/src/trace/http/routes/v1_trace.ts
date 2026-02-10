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

// 에러 코드 상수 (사용자 값 포함 금지)
const ERROR = {
  UNAUTHORIZED: "UNAUTHORIZED",
  TRACE_EVENT_INVALID: "TRACE_EVENT_INVALID",
  TRACE_STORE_FAILED: "TRACE_STORE_FAILED",
} as const;

// API 키: env 없으면 빈 문자열 (fail-closed)
const ALLOWED_API_KEY = process.env.TRACE_API_KEY ?? "";
const HAS_KEY = ALLOWED_API_KEY.length > 0;

/**
 * 로컬 요청인지 확인
 */
function isLocalRequest(req: Request): boolean {
  const ip = req.ip || req.socket.remoteAddress || "";
  const normalizedIp = ip.replace(/^::ffff:/, ""); // IPv6-mapped IPv4
  
  // 빈 IP는 fail-closed (거부)
  if (!normalizedIp || normalizedIp === "") {
    return false;
  }
  
  return (
    normalizedIp === "127.0.0.1" ||
    normalizedIp === "::1" ||
    normalizedIp === "localhost"
  );
}

/**
 * 접근 잠금: 로컬-only 또는 인증 필수
 * IPv6/::ffff: 포함
 */
function checkAccess(req: Request): { allowed: boolean; reason?: string } {
  // 1) 로컬-only 확인
  if (isLocalRequest(req)) {
    return { allowed: true };
  }

  // 2) 외부 접근: 키가 반드시 있어야 함 (env 누락 시 fail-closed)
  if (!HAS_KEY) {
    return { allowed: false, reason: ERROR.UNAUTHORIZED };
  }

  // 3) 키 값 매칭 (존재만 금지)
  const apiKey = req.headers["x-api-key"];
  if (apiKey && typeof apiKey === "string" && apiKey === ALLOWED_API_KEY) {
    return { allowed: true };
  }

  // 4) 0.0.0.0 바인딩 통과 금지
  const ip = req.ip || req.socket.remoteAddress || "";
  const normalizedIp = ip.replace(/^::ffff:/, "");
  if (normalizedIp === "0.0.0.0" || normalizedIp === "::") {
    return { allowed: false, reason: ERROR.UNAUTHORIZED };
  }

  return { allowed: false, reason: ERROR.UNAUTHORIZED };
}

export function buildTraceRouter(store: TraceStore) {
  const r = express.Router();
  r.use(express.json({ limit: "32kb" }));

  r.post("/v1/trace", async (req: Request, res: Response) => {
    const requestId = (req.body as any)?.request_id || "";
    
    try {
      // 접근 잠금 확인
      const access = checkAccess(req);
      if (!access.allowed) {
        // 실패 응답에 원문/세부 내용 포함 금지 (짧은 코드만)
        return res.status(403).json({
          ok: false,
          error_code: access.reason || ERROR.UNAUTHORIZED,
          request_id: requestId,
        });
      }

      // ingest (저장 전 검증은 store.ingest 내부에서 수행)
      const result = await store.ingest(req.body);
      
      res.json({
        ok: true,
        inserted: result.inserted,
        request_id: requestId,
      });
    } catch (e: any) {
      // 실패 응답에 원문/세부 내용 포함 금지 (짧은 코드만)
      // e.message는 절대 노출하지 않음
      let errorCode = ERROR.TRACE_STORE_FAILED;
      
      // TraceError 타입 확인 (내부에서 던진 에러)
      if (e?.code === "TRACE_EVENT_INVALID" || e?.message?.includes("TRACE_EVENT_V1")) {
        errorCode = ERROR.TRACE_EVENT_INVALID;
      }
      
      res.status(400).json({
        ok: false,
        error_code: errorCode,
        request_id: requestId,
      });
    }
  });

  return r;
}

