import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

function json(res, code, obj) {
  res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(obj));
}

function nowIsoUtc() { return new Date().toISOString(); }

const FORBIDDEN_KEYS = [
  "raw_text", "prompt", "messages", "document_body", "content", "body", "payload", "input", "output"
];

function isPlainObject(x) {
  return !!x && typeof x === "object" && !Array.isArray(x);
}

function hasForbiddenTopLevelKeys(obj) {
  const keys = Object.keys(obj);
  return keys.some((k) => FORBIDDEN_KEYS.includes(k));
}

function validateMetaOnly(obj) {
  // top-level allowlist
  const allowedTop = new Set(["request_id", "mode", "signals"]);
  if (!isPlainObject(obj)) return { ok: false, reason: "BAD_BODY" };

  const extraTop = Object.keys(obj).filter((k) => !allowedTop.has(k));
  if (extraTop.length) return { ok: false, reason: "META_ONLY_TOPLEVEL_VIOLATION" };
  if (hasForbiddenTopLevelKeys(obj)) return { ok: false, reason: "FORBIDDEN_KEY" };

  if (typeof obj.request_id !== "string" || obj.request_id.length < 6) return { ok: false, reason: "BAD_REQUEST_ID" };
  if (obj.mode !== "live" && obj.mode !== "mock") return { ok: false, reason: "BAD_MODE" };

  if (!isPlainObject(obj.signals)) return { ok: false, reason: "BAD_SIGNALS" };

  const keys = Object.keys(obj.signals);
  if (keys.length > 64) return { ok: false, reason: "TOO_MANY_KEYS" };

  for (const k of keys) {
    if (FORBIDDEN_KEYS.includes(k)) return { ok: false, reason: "FORBIDDEN_KEY" };

    const v = obj.signals[k];
    const t = typeof v;
    const ok = v === null || t === "string" || t === "number" || t === "boolean";
    if (!ok) return { ok: false, reason: "NON_META_VALUE" };

    if (t === "string") {
      if (v.length > 64) return { ok: false, reason: "STRING_TOO_LONG" };
      if (v.includes("\n") || v.includes("\r")) return { ok: false, reason: "MULTILINE_STRING" };
      // 간단한 식별자 덤프 차단(예: JWT, 긴 hex)
      if (/^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/.test(v)) return { ok: false, reason: "JWT_LIKE" };
      if (/^[0-9a-f]{64,}$/i.test(v)) return { ok: false, reason: "LONG_HEX" };
    }
  }

  return { ok: true };
}

export async function startMetaOnlyNegativeServer() {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const html = await readFile(path.join(__dirname, "meta_only_negative_page.html"), "utf8");
  const pageJs = await readFile(path.join(__dirname, "meta_only_negative_page.mjs"), "utf8");

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://${req.headers.host}`);

      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(html);
        return;
      }
      if (url.pathname === "/meta_only_negative_page.mjs") {
        res.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
        res.end(pageJs);
        return;
      }

      if (url.pathname === "/api/meta" && req.method === "POST") {
        let body = "";
        for await (const c of req) body += c;

        let parsed;
        try { parsed = JSON.parse(body); } catch {
          json(res, 400, { status: "DENY", reason_code: "BAD_JSON" });
          return;
        }

        const v = validateMetaOnly(parsed);
        if (!v.ok) {
          json(res, 400, { status: "DENY", reason_code: v.reason, ts_utc: nowIsoUtc() });
          return;
        }

        json(res, 200, { status: "OK", ts_utc: nowIsoUtc() });
        return;
      }

      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not Found");
    } catch {
      res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      res.end("Internal Error");
    }
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const addr = server.address();
  if (!addr || typeof addr === "string") throw new Error("server.address() failed");

  const baseURL = `http://127.0.0.1:${addr.port}`;
  return { server, baseURL };
}

