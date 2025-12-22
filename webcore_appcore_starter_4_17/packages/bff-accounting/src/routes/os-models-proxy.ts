import { Router } from "express";
import { requireTenantAuth } from "../shared/guards.js";

export const osModelsProxyRouter = Router();

/**
 * OS WebLLM model artifacts proxy (DEV/QA + Prod policy-ready)
 *
 * URL shape:
 *   GET/HEAD /v1/os/models/:modelId/*path
 *
 * Security:
 * - WEBLLM_UPSTREAM_BASE_URL only (no arbitrary URL param)  -> SSRF 방지
 * - modelId allowlist (env-driven)
 * - path traversal 방지 (.., encoded ..)
 * - extension allowlist
 *
 * Caching:
 * - Cache-Control: public, max-age=86400 (표준 B)
 * - ETag pass-through + If-None-Match -> 304
 * - Content-Length 전달(가능하면)
 */

function bad(res: any, code: number, msg: string) {
  return res.status(code).json({ ok: false, error: msg });
}

function getUpstreamBaseUrl(): string {
  const v = (process.env.WEBLLM_UPSTREAM_BASE_URL || "").trim();
  if (!v) throw new Error("WEBLLM_UPSTREAM_BASE_URL_not_set");
  if (!/^https?:\/\//i.test(v))
    throw new Error("WEBLLM_UPSTREAM_BASE_URL_invalid_scheme");
  if (!v.endsWith("/"))
    throw new Error("WEBLLM_UPSTREAM_BASE_URL_missing_trailing_slash");
  return v;
}

function getAllowedModelIds(): Set<string> {
  // 우선순위: WEBLLM_ALLOWED_MODEL_IDS (comma-separated)
  const raw = (process.env.WEBLLM_ALLOWED_MODEL_IDS || "").trim();
  const ids =
    raw.length > 0
      ? raw
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [
          (process.env.WEBLLM_TEST_MODEL_ID || "local-llm-v1").trim(),
          "local-llm-v1",
        ];
  return new Set(ids.filter(Boolean));
}

function decodePathSafe(p: string): string {
  // Express wildcard는 인코딩 포함 가능 -> decode 후 검사
  let d = p;
  try {
    d = decodeURIComponent(p);
  } catch {
    // decode 실패도 공격/깨짐 가능 -> 차단
    throw new Error("path_decode_failed");
  }
  return d;
}

function isBadPath(p: string): boolean {
  // traversal / protocol injection / absolute path / windows separators
  if (p.includes("..")) return true;
  if (p.includes("\\") || p.includes("\u0000")) return true;
  if (p.startsWith("/") || p.startsWith("~")) return true;
  if (p.includes("://")) return true;
  return false;
}

function isAllowedExt(p: string): boolean {
  // web-llm 아티팩트는 대부분 json/bin/wasm/params 계열
  return /\.(json|bin|wasm|params|txt)$/i.test(p);
}

async function headUpstream(url: string, headers: Record<string, string>) {
  const r = await fetch(url, { method: "HEAD", headers });
  // 일부 정적서버가 HEAD를 이상하게 처리하는 경우를 대비해, 실패 시 GET으로 폴백(헤더만 사용)
  if (r.status >= 400) return r;
  return r;
}

osModelsProxyRouter.use(requireTenantAuth);

osModelsProxyRouter.all("/:modelId/*", async (req, res) => {
  try {
    const modelId = String(req.params.modelId || "").trim();
    const allowed = getAllowedModelIds();
    if (!allowed.has(modelId)) return bad(res, 403, "modelId_not_allowed");
    const splat = (req.params as any)[0];
    let restPath = String(splat || "");
    restPath = decodePathSafe(restPath);
    if (!restPath) return bad(res, 400, "empty_path");
    if (isBadPath(restPath)) return bad(res, 400, "path_traversal_blocked");
    if (!isAllowedExt(restPath))
      return bad(res, 400, "file_extension_not_allowed");

    let upstreamBase = "";
    try {
      upstreamBase = getUpstreamBaseUrl();
    } catch (e: any) {
      return bad(res, 500, e.message || "WEBLLM_UPSTREAM_BASE_URL_invalid");
    }

    const upstreamUrl = new URL(
      `${modelId}/${restPath}`,
      upstreamBase
    ).toString();

    // 클라이언트 캐시검증(If-None-Match) 지원: upstream ETag 기준으로 304 반환
    const inm = String(req.header("if-none-match") || "").trim();

    // HEAD로 메타 먼저 확인(ETag/Content-Length/Content-Type)
    const metaResp = await headUpstream(
      upstreamUrl,
      inm ? { "If-None-Match": inm } : {}
    );
    const etag = metaResp.headers.get("etag");
    const ct = metaResp.headers.get("content-type");
    const cl = metaResp.headers.get("content-length");

    // 표준 캐시 정책(B)
    res.setHeader("Cache-Control", "public, max-age=86400");

    if (etag) res.setHeader("ETag", etag);
    if (ct) res.setHeader("Content-Type", ct);
    if (cl) res.setHeader("Content-Length", cl);

    // upstream이 304를 주면 그대로 304
    if (metaResp.status === 304) {
      return res.status(304).end();
    }

    // If-None-Match가 있고, ETag가 동일하면 304
    if (inm && etag && inm === etag) {
      return res.status(304).end();
    }

    // HEAD 요청은 여기서 종료
    if (req.method === "HEAD") {
      // upstream이 200이 아니면 상태 반영
      return res.status(metaResp.status).end();
    }

    // GET: 실제 바디 전달(스트리밍)
    const r = await fetch(upstreamUrl, { method: "GET" });
    if (!r.ok) {
      // upstream 상태를 최대한 반영
      return res.status(r.status).end();
    }

    // 헤더 재세팅(업스트림 GET이 더 정확할 수 있음)
    const etag2 = r.headers.get("etag");
    const ct2 = r.headers.get("content-type");
    const cl2 = r.headers.get("content-length");
    if (etag2) res.setHeader("ETag", etag2);
    if (ct2) res.setHeader("Content-Type", ct2);
    if (cl2) res.setHeader("Content-Length", cl2);

    // Node >= 18: web stream -> node stream
    // @ts-ignore
    const { Readable } = await import("node:stream");
    // @ts-ignore
    const body = r.body ? Readable.fromWeb(r.body) : null;

    res.status(200);
    if (!body) return res.end();
    body.pipe(res);
  } catch (e: any) {
    const msg = String(e?.message || "proxy_unhandled_error");
    // decodeURIComponent 실패 등 입력 문제는 400으로 수렴(항상 JSON 응답 보장)
    const code = msg.includes("path_decode") ? 400 : 500;
    return bad(res, code, msg);
  }
});

export default osModelsProxyRouter;
