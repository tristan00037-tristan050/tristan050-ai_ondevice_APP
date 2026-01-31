import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

function nowIsoUtc() { return new Date().toISOString(); }

export async function startP95MarksServer() {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const html = await readFile(path.join(__dirname, "p95_marks_page.html"), "utf8");
  const pageJs = await readFile(path.join(__dirname, "p95_marks_page.mjs"), "utf8");

  const requiredHeaders = [
    "x-request-id",
    "x-device-id",
    "x-role",
    "x-client-version",
    "x-mode",
    "x-ts-utc",
    "x-policy-version",
  ];

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://${req.headers.host}`);

      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(html);
        return;
      }

      if (url.pathname === "/p95_marks_page.mjs") {
        res.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
        res.end(pageJs);
        return;
      }

      // "runtime-like" endpoint (headers + 3 blocks)
      if (url.pathname === "/api/three_blocks" && req.method === "POST") {
        const missing = requiredHeaders.filter((h) => !(h in req.headers));
        if (missing.length) {
          res.writeHead(400, { "content-type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "HEADER_MISSING", missing }));
          return;
        }

        let body = "";
        for await (const chunk of req) body += chunk;

        let parsed;
        try { parsed = JSON.parse(body); } catch {
          res.writeHead(400, { "content-type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_JSON" }));
          return;
        }

        // meta-only top-level allowlist
        const allowedTop = new Set(["request_id", "mode", "signals"]);
        const extraTop = Object.keys(parsed ?? {}).filter((k) => !allowedTop.has(k));
        if (extraTop.length) {
          res.writeHead(400, { "content-type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "META_ONLY_TOPLEVEL_VIOLATION", extraTop }));
          return;
        }

        if (typeof parsed.request_id !== "string" || parsed.request_id.length < 6) {
          res.writeHead(400, { "content-type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ status: "DENY", reason_code: "BAD_REQUEST_ID" }));
          return;
        }

        // runtime-like headers
        const latencyMs = 3; // deterministic
        const manifestSha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"; // deterministic dummy

        res.writeHead(200, {
          "content-type": "application/json; charset=utf-8",
          "x-os-algo-latency-ms": String(latencyMs),
          "x-os-algo-manifest-sha256": manifestSha,
          "x-os-ts-utc": nowIsoUtc(),
        });

        res.end(JSON.stringify({
          ok: true,
          blocks: {
            b1: ["상태: OK", `req:${parsed.request_id.slice(0, 8)}`],
            b2: "P95 marks contract sealed",
            b3: ["next: auditv2", "next: apply fail-closed"],
          }
        }));
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

