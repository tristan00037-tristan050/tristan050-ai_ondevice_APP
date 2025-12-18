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
  if (!ALLOWED_MODEL_IDS.has(modelId)) return bad(res, 403, "modelId_not_allowed");
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
  res.setHeader("cache-control", "public, max-age=3600");

  const buf = Buffer.from(await r.arrayBuffer());
  return res.send(buf);
});

export default osModelsProxyRouter;
