import { Router } from "express";
import { requireTenantAuth, requireRole } from "../shared/guards.js";
import { validateMetaOnlyOrThrow, generateThreeBlocks, getAlgoCoreSignerOrThrow, signManifest } from "../lib/osAlgoCore.js";

const router = Router();

// 부트 시점 fail-closed (prod 모드면 키 미설정 시 즉시 throw -> index.ts에서 import 시점에 터짐)
try {
  getAlgoCoreSignerOrThrow();
} catch (e: any) {
  // prod일 때만 치명, dev는 여기 도달하지 않음(모듈에서 dev는 임시키 생성)
  const mode = (process.env.ALGO_CORE_MODE || "dev").trim();
  if (mode === "prod") {
    // import 시점에서 서버가 아예 뜨지 않게(부트 fail-closed)
    throw e;
  }
}

// POST /v1/os/algo/three-blocks
router.post(
  "/three-blocks",
  requireTenantAuth,
  requireRole("operator"),
  async (req: any, res) => {
    const t0 = process.hrtime.bigint();
    try {
      validateMetaOnlyOrThrow(req.body);

      const blocks = generateThreeBlocks(req.body);
      // exactly 3 blocks (fail-closed)
      if (typeof blocks !== "object" || Object.keys(blocks).length !== 3) {
        return res.status(500).json({ ok: false, error_code: "ALGO_BLOCKS_NOT_THREE_FAILCLOSED" });
      }

      const manifestPayload = {
        schema_name: "ALGO_CORE_RUNTIME_MANIFEST_V1",
        created_at_utc: new Date().toISOString(),
        tenant: String(req.headers["x-tenant"] || ""),
        request_id: String(req.body.request_id || req.id || ""),
        intent: String(req.body.intent || ""),
        model_id: String(req.body.model_id || ""),
        blocks,
      };

      const sig = signManifest(manifestPayload);

      const t1 = process.hrtime.bigint();
      const ms = Number(t1 - t0) / 1e6;
      res.setHeader("X-OS-Algo-Latency-Ms", ms.toFixed(3));
      res.setHeader("X-OS-Algo-Manifest-SHA256", sig.manifest_sha256);

      return res.json({
        ok: true,
        blocks,
        manifest: { sha256: sig.manifest_sha256 },
        signature: {
          b64: sig.signature_b64,
          public_key_b64: sig.public_key_b64,
          key_id: sig.key_id,
          mode: sig.mode,
        },
      });
    } catch (e: any) {
      const msg = String(e?.message || "ALGO_CORE_UNHANDLED");
      // meta-only 위반은 400으로 수렴
      const code = msg.startsWith("META_ONLY_") ? 400 : 500;
      return res.status(code).json({
        ok: false,
        error_code: msg,
        request_id: String(req.body?.request_id || req.id || ""),
      });
    }
  }
);

export default router;
