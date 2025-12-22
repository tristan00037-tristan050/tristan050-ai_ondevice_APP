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

// 헤더 allowlist: 업스트림에서 클라이언트로 전달할 헤더만 허용
const ALLOWED_HEADERS = new Set([
  "content-type",
  "etag",
  "cache-control",
  "content-length",
  "accept-ranges",
  "content-range",
  "last-modified",
]);

function shouldForwardHeader(name: string): boolean {
  return ALLOWED_HEADERS.has(name.toLowerCase());
}

// Timeout 설정 (기본 60초, 대용량 파일 고려)
const UPSTREAM_TIMEOUT_MS = parseInt(
  process.env.WEBLLM_UPSTREAM_TIMEOUT_MS || "60000",
  10
);

async function headUpstream(
  url: string,
  headers: Record<string, string>,
  signal?: AbortSignal
) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  try {
    const r = await fetch(url, {
      method: "HEAD",
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    // 일부 정적서버가 HEAD를 이상하게 처리하는 경우를 대비해, 실패 시 GET으로 폴백(헤더만 사용)
    if (r.status >= 400) return r;
    return r;
  } catch (e: any) {
    clearTimeout(timeoutId);
    if (e.name === "AbortError") {
      throw new Error("upstream_timeout");
    }
    throw e;
  }
}

async function fetchUpstream(
  url: string,
  headers: Record<string, string>,
  signal?: AbortSignal
) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  try {
    const r = await fetch(url, {
      method: "GET",
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return r;
  } catch (e: any) {
    clearTimeout(timeoutId);
    if (e.name === "AbortError") {
      throw new Error("upstream_timeout");
    }
    throw e;
  }
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

    // 클라이언트 요청 취소 감지
    const clientAborted = new AbortController();
    req.on("close", () => clientAborted.abort());

    // Range 요청 지원: 클라이언트가 Range 헤더를 보내면 upstream에 전달
    const rangeHeader = req.header("range");
    const inm = String(req.header("if-none-match") || "").trim();

    // upstream 요청 헤더 구성
    const upstreamHeaders: Record<string, string> = {};
    if (inm) upstreamHeaders["If-None-Match"] = inm;
    if (rangeHeader) upstreamHeaders["Range"] = rangeHeader;

    // HEAD로 메타 먼저 확인(ETag/Content-Length/Content-Type/Accept-Ranges)
    const metaResp = await headUpstream(
      upstreamUrl,
      upstreamHeaders,
      clientAborted.signal
    );

    // 헤더 전달 (allowlist 기반)
    for (const [key, value] of metaResp.headers.entries()) {
      if (shouldForwardHeader(key)) {
        res.setHeader(key, value);
      }
    }

    // 표준 캐시 정책(B) - 프록시 정책이 우선
    res.setHeader("Cache-Control", "public, max-age=86400");

    // upstream이 304를 주면 그대로 304
    if (metaResp.status === 304) {
      return res.status(304).end();
    }

    // If-None-Match가 있고, ETag가 동일하면 304
    const etag = metaResp.headers.get("etag");
    if (inm && etag && inm === etag) {
      return res.status(304).end();
    }

    // HEAD 요청은 여기서 종료
    if (req.method === "HEAD") {
      return res.status(metaResp.status).end();
    }

    // GET: 실제 바디 전달(스트리밍)
    const r = await fetchUpstream(
      upstreamUrl,
      upstreamHeaders,
      clientAborted.signal
    );

    if (!r.ok) {
      // upstream 상태를 최대한 반영
      return res.status(r.status).end();
    }

    // Range 요청 응답(206) 처리
    if (r.status === 206) {
      res.status(206);
      // Content-Range 헤더는 이미 allowlist로 전달됨
    } else {
      res.status(200);
    }

    // 헤더 재세팅(업스트림 GET이 더 정확할 수 있음, allowlist 적용)
    for (const [key, value] of r.headers.entries()) {
      if (shouldForwardHeader(key)) {
        res.setHeader(key, value);
      }
    }

    // Node >= 18: web stream -> node stream (메모리 효율적 스트리밍)
    // @ts-ignore
    const { Readable } = await import("node:stream");
    // @ts-ignore
    const body = r.body ? Readable.fromWeb(r.body) : null;

    if (!body) return res.end();

    // 스트리밍 파이프 (클라이언트 취소 시 자동 정리)
    body.pipe(res);

    // 클라이언트 연결 종료 시 스트림 정리
    req.on("close", () => {
      if (body && !body.destroyed) {
        body.destroy();
      }
    });
  } catch (e: any) {
    const msg = String(e?.message || "proxy_unhandled_error");
    // decodeURIComponent 실패 등 입력 문제는 400으로 수렴(항상 JSON 응답 보장)
    const code = msg.includes("path_decode") ? 400 : 500;
    return bad(res, code, msg);
  }
});

export default osModelsProxyRouter;
