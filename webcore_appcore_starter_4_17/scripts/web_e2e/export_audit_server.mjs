import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import crypto from "node:crypto";

function sha256Hex(s) {
  return crypto.createHash("sha256").update(String(s)).digest("hex");
}

function ulidLike() {
  // 간단한 ULID 스타일(테스트용): time + random
  return `${Date.now().toString(36)}_${crypto.randomBytes(10).toString("hex")}`;
}

function nowIsoUtc() { return new Date().toISOString(); }

export async function startExportAuditServer() {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const html = await readFile(path.join(__dirname, "export_audit_page.html"), "utf8");
  const pageJs = await readFile(path.join(__dirname, "export_audit_page.mjs"), "utf8");

  // Live 정책 헤더 번들 최소 세트(UX-01과 동일 계열)
  const requiredHeaders = [
    "x-request-id",
    "x-device-id",
    "x-role",
    "x-client-version",
    "x-mode",
    "x-ts-utc",
    "x-policy-version",
  ];

  // idempotency store: idem_key -> audit_id
  const idemToAudit = new Map();
  let auditCountTotal = 0;

  function json(res, code, obj) {
    res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(obj));
  }

  function readBody(req) {
    return new Promise((resolve, reject) => {
      let body = "";
      req.on("data", (c) => { body += c; });
      req.on("end", () => resolve(body));
      req.on("error", reject);
    });
  }

  function parseJsonOrDeny(body, res) {
    let parsed;
    try { parsed = JSON.parse(body); } catch {
      json(res, 400, { status: "DENY", reason_code: "BAD_JSON" });
      return null;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      json(res, 400, { status: "DENY", reason_code: "BAD_BODY" });
      return null;
    }
    return parsed;
  }

  // meta-only allowlist(최소)
  function validateMetaOnlyTop(parsed, allowedTop, res) {
    const extra = Object.keys(parsed).filter((k) => !allowedTop.has(k));
    if (extra.length) {
      json(res, 400, { status: "DENY", reason_code: "META_ONLY_TOPLEVEL_VIOLATION", extra });
      return false;
    }
    return true;
  }

  function validateSignals(signals, res) {
    if (!signals || typeof signals !== "object" || Array.isArray(signals)) {
      json(res, 400, { status: "DENY", reason_code: "BAD_SIGNALS" });
      return false;
    }
    for (const [k, v] of Object.entries(signals)) {
      const t = typeof v;
      const ok = v === null || t === "string" || t === "number" || t === "boolean";
      if (!ok) {
        json(res, 400, { status: "DENY", reason_code: "NON_META_VALUE", key: k, type: t });
        return false;
      }
      if (t === "string") {
        if (v.length > 64 || v.includes("\n") || v.includes("\r")) {
          json(res, 400, { status: "DENY", reason_code: "STRING_TOO_LONG_OR_MULTILINE", key: k });
          return false;
        }
      }
    }
    return true;
  }

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://${req.headers.host}`);

      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(html);
        return;
      }

      if (url.pathname === "/export_audit_page.mjs") {
        res.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
        res.end(pageJs);
        return;
      }

      if (url.pathname === "/api/audit_stats" && req.method === "GET") {
        json(res, 200, { status: "OK", audit_count_total: auditCountTotal });
        return;
      }

      // 1) PREVIEW
      if (url.pathname === "/api/preview" && req.method === "POST") {
        const missingHeaders = requiredHeaders.filter((h) => !(h in req.headers));
        if (missingHeaders.length) {
          json(res, 400, { status: "DENY", reason_code: "HEADER_MISSING", missing: missingHeaders });
          return;
        }

        const body = await readBody(req);
        const parsed = parseJsonOrDeny(body, res);
        if (!parsed) return;

        const allowedTop = new Set(["request_id", "mode", "signals"]);
        if (!validateMetaOnlyTop(parsed, allowedTop, res)) return;

        if (typeof parsed.request_id !== "string" || parsed.request_id.length < 6) {
          json(res, 400, { status: "DENY", reason_code: "BAD_REQUEST_ID" });
          return;
        }
        if (parsed.mode !== "live") {
          json(res, 400, { status: "DENY", reason_code: "MODE_MISMATCH" });
          return;
        }
        if (!validateSignals(parsed.signals, res)) return;

        const export_token = ulidLike();
        const export_token_hash = sha256Hex(export_token);
        json(res, 200, {
          status: "OK",
          export_token,
          export_token_hash,
          preview_utc: nowIsoUtc(),
        });
        return;
      }

      // 2) APPROVE (멱등 + audit 누락 0)
      if (url.pathname === "/api/approve" && req.method === "POST") {
        const missingHeaders = requiredHeaders.filter((h) => !(h in req.headers));
        if (missingHeaders.length) {
          json(res, 400, { status: "DENY", reason_code: "HEADER_MISSING", missing: missingHeaders });
          return;
        }

        const idem = req.headers["x-idempotency-key"];
        if (!idem || typeof idem !== "string" || idem.length < 16) {
          json(res, 400, { status: "DENY", reason_code: "IDEMPOTENCY_MISSING" });
          return;
        }

        const body = await readBody(req);
        const parsed = parseJsonOrDeny(body, res);
        if (!parsed) return;

        const allowedTop = new Set(["request_id", "mode", "export_token_hash", "policy_version", "signals"]);
        if (!validateMetaOnlyTop(parsed, allowedTop, res)) return;

        if (typeof parsed.request_id !== "string" || parsed.request_id.length < 6) {
          json(res, 400, { status: "DENY", reason_code: "BAD_REQUEST_ID" });
          return;
        }
        if (parsed.mode !== "live") {
          json(res, 400, { status: "DENY", reason_code: "MODE_MISMATCH" });
          return;
        }
        if (typeof parsed.export_token_hash !== "string" || parsed.export_token_hash.length < 16) {
          json(res, 400, { status: "DENY", reason_code: "BAD_EXPORT_TOKEN_HASH" });
          return;
        }
        if (typeof parsed.policy_version !== "string" || parsed.policy_version.length < 1) {
          json(res, 400, { status: "DENY", reason_code: "BAD_POLICY_VERSION" });
          return;
        }
        if (!validateSignals(parsed.signals, res)) return;

        // expected idempotency_key = sha256(request_id + export_token_hash + policy_version)
        const expected = sha256Hex(`${parsed.request_id}:${parsed.export_token_hash}:${parsed.policy_version}`);
        if (idem !== expected) {
          json(res, 400, { status: "DENY", reason_code: "IDEMPOTENCY_MISMATCH" });
          return;
        }

        // 멱등 처리: 같은 idem이면 같은 audit_id 반환, auditCountTotal은 1회만 증가
        let audit_id = idemToAudit.get(idem);
        let first = false;
        if (!audit_id) {
          audit_id = ulidLike();
          idemToAudit.set(idem, audit_id);
          auditCountTotal += 1;
          first = true;
        }

        json(res, 200, {
          status: "OK",
          approved: true,
          audit_event_v2_id: audit_id,
          idempotent_first_write: first,
          approved_utc: nowIsoUtc(),
        });
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

