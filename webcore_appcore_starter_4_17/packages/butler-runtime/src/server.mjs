import http from "node:http";
import crypto from "node:crypto";
import { assertInternalUrlOrThrow } from "./safe_net.mjs";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
// 레포 루트까지: src -> butler-runtime -> packages -> webcore_appcore_starter_4_17 -> 레포 루트 (../../../../)
const { validateMetaOnlyOrThrow } = require("../../../../packages/common/meta_only/validator_v1.cjs");

function json(res, code, obj) {
  const body = Buffer.from(JSON.stringify(obj), "utf8");
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Content-Length": body.length });
  res.end(body);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      try {
        const s = Buffer.concat(chunks).toString("utf8");
        resolve(s ? JSON.parse(s) : {});
      } catch (e) { reject(e); }
    });
    req.on("error", reject);
  });
}

function isPlainObject(x) {
  return x && typeof x === "object" && !Array.isArray(x);
}

// v0: 모델 추론 대신, 3블록 "형태"만 반환(후속 PR에서 modelpack/runtime 실행으로 교체)
function makeThreeBlocks(meta) {
  return {
    block_1_core: ["v0 runtime skeleton", `dept=${meta.dept}`, `tier=${meta.tier}`],
    block_2_decision: "v0: runtime is alive; model execution will be attached via Model Pack",
    block_3_next: ["keep gateway baseline SEALED", "attach model pack loader next", "wire shadow mode from gateway"]
  };
}

const PORT = Number(process.env.RUNTIME_PORT || "8091");

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "POST" && req.url === "/v1/runtime/three-blocks") {
      const body = await parseBody(req);
      validateMetaOnlyOrThrow(body, "butler-runtime/server.mjs");

      // 코드 레벨 외부 호출 0: (현재는 실제 호출 없음) 래퍼 동작 확인은 verify에서 수행
      // assertInternalUrlOrThrow("https://example.com");

      const blocks = makeThreeBlocks(body);
      const t0 = Date.now();
      const t1 = Date.now();
      return json(res, 200, {
        ok: true,
        request_id: String(body.request_id),
        blocks,
        latency_ms: t1 - t0
      });
    }
    if (req.method === "POST" && req.url === "/v0/runtime/shadow") {
      const body = await parseBody(req);
      validateMetaOnlyOrThrow(body, "butler-runtime/server.mjs");

      const t0 = Date.now();
      // meta-only 요청 기반 SHA256
      const metaJson = JSON.stringify(body);
      const manifestSha256 = crypto.createHash("sha256").update(metaJson, "utf8").digest("hex");
      const t1 = Date.now();
      const latencyMs = t1 - t0;

      // 204 No Content: 바디 없이 헤더만
      res.writeHead(204, {
        "X-OS-Algo-Latency-Ms": latencyMs.toString(),
        "X-OS-Algo-Manifest-SHA256": manifestSha256,
      });
      return res.end();
    }
    return json(res, 404, { ok: false, error_code: "NOT_FOUND" });
  } catch (e) {
    return json(res, 400, { ok: false, error_code: String(e?.message || "BAD_REQUEST") });
  }
});

if (process.argv.includes("--smoke")) {
  // smoke mode: start then print a ready line
  server.listen(PORT, "127.0.0.1", () => {
    console.log(`RUNTIME_LISTENING=1 PORT=${PORT}`);
  });
} else {
  server.listen(PORT, "127.0.0.1", () => {
    console.log(`RUNTIME_LISTENING=1 PORT=${PORT}`);
  });
}
