import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

export async function startModeSwitchServer() {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const html = await readFile(path.join(__dirname, "mode_switch_page.html"), "utf8");
  const pageJs = await readFile(path.join(__dirname, "mode_switch_page.mjs"), "utf8");

  const requiredHeaders = [
    "x-request-id",
    "x-device-id",
    "x-role",
    "x-client-version",
    "x-mode",
    "x-ts-utc",
  ];

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://${req.headers.host}`);

      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(html);
        return;
      }

      if (url.pathname === "/mode_switch_page.mjs") {
        res.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
        res.end(pageJs);
        return;
      }

      if (url.pathname === "/api/echo" && req.method === "POST") {
        const missing = requiredHeaders.filter((h) => !(h in req.headers));
        if (missing.length) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "HEADER_MISSING", missing }));
          return;
        }

        let body = "";
        for await (const chunk of req) body += chunk;

        let parsed;
        try { parsed = JSON.parse(body); } catch {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_JSON" }));
          return;
        }

        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_BODY" }));
          return;
        }

        const allowedTop = new Set(["request_id", "mode", "signals"]);
        const extraTop = Object.keys(parsed).filter((k) => !allowedTop.has(k));
        if (extraTop.length) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "META_ONLY_TOPLEVEL_VIOLATION", extraTop }));
          return;
        }

        if (typeof parsed.request_id !== "string" || parsed.request_id.length < 6) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_REQUEST_ID" }));
          return;
        }

        if (parsed.mode !== "live") {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "MODE_MISMATCH" }));
          return;
        }

        if (!parsed.signals || typeof parsed.signals !== "object" || Array.isArray(parsed.signals)) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_SIGNALS" }));
          return;
        }

        for (const [k, v] of Object.entries(parsed.signals)) {
          const t = typeof v;
          const ok = v === null || t === "string" || t === "number" || t === "boolean";
          if (!ok) {
            res.writeHead(400, { "content-type": "application/json" });
            res.end(JSON.stringify({ status: "DENY", reason_code: "NON_META_VALUE", key: k, type: t }));
            return;
          }
          if (t === "string") {
            if (v.length > 64 || v.includes("\n") || v.includes("\r")) {
              res.writeHead(400, { "content-type": "application/json" });
              res.end(JSON.stringify({ status: "DENY", reason_code: "STRING_TOO_LONG_OR_MULTILINE", key: k }));
              return;
            }
          }
        }

        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "OK", echo: { request_id: parsed.request_id } }));
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
