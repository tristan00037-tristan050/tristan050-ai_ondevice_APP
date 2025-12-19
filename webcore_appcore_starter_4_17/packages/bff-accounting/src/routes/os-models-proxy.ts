import { Router } from "express";
import { requireTenantAuth } from "../shared/guards.js";

export const osModelsProxyRouter = Router();

/**
 * DEV/QA 모델 아티팩트 프록시 (외부 URL 직접 fetch 금지)
 *
 * 호출 예:
 *   GET /v1/os/models/<modelId>/<filePath>
 *
 * upstream(실제 저장소)는 WEBLLM_UPSTREAM_BASE_URL로만 고정.
 * modelId는 allowlist로 제한.
 */
const ALLOWED_MODEL_IDS = new Set([
  // TODO: 허용 모델만 남기세요
  "local-llm-v1",
]);

const UPSTREAM_BASE = process.env.WEBLLM_UPSTREAM_BASE_URL || "";

function bad(res: any, code: number, msg: string) {
  return res.status(code).json({ ok: false, error: msg });
}

osModelsProxyRouter.get("/:modelId/*", requireTenantAuth, async (req, res) => {
  const modelId = String(req.params.modelId || "");
  const restPath = String(req.params[0] || "");

  if (!UPSTREAM_BASE) return bad(res, 500, "WEBLLM_UPSTREAM_BASE_URL_not_set");
  if (!ALLOWED_MODEL_IDS.has(modelId))
    return bad(res, 403, "modelId_not_allowed");
  if (restPath.includes("..")) return bad(res, 400, "path_traversal_blocked");

  // 필요한 확장자만 허용(원하시면 추가)
  if (!/\.(json|bin|wasm|params|txt)$/i.test(restPath)) {
    return bad(res, 400, "file_extension_not_allowed");
  }

  const upstream = new URL(`${modelId}/${restPath}`, UPSTREAM_BASE).toString();
  const r = await fetch(upstream);

  res.status(r.status);
  const ct = r.headers.get("content-type");
  if (ct) res.setHeader("content-type", ct);

  // ✅ E06-3: 캐시 정책 강화 (ETag + Cache-Control)
  // 모델 아티팩트는 버전이 바뀌면 새로 받아야 하므로, ETag로 무효화 전략 지원
  const etag = r.headers.get("etag");
  if (etag) {
    res.setHeader("etag", etag);
    // 클라이언트가 If-None-Match로 요청하면 304 반환
    const ifNoneMatch = req.headers["if-none-match"];
    if (ifNoneMatch === etag) {
      return res.status(304).end();
    }
  }

  // ✅ E06-3: 재방문 성능 고정 - 모델 아티팩트는 오래 캐시 가능
  // 버전 변경 시 ETag로 무효화되므로 max-age를 길게 설정
  res.setHeader("cache-control", "public, max-age=86400, immutable");

  // Content-Length 전달 (클라이언트가 진행률 표시 가능)
  const contentLength = r.headers.get("content-length");
  if (contentLength) {
    res.setHeader("content-length", contentLength);
  }

  const buf = Buffer.from(await r.arrayBuffer());
  return res.send(buf);
});

export default osModelsProxyRouter;
