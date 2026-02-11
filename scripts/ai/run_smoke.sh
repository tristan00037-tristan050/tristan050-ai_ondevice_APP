#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest
OUT="ai/reports/latest/summary.md"

# dist 엔트리(verify 스크립트도 dist를 사용합니다)
DIST="webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js"

if [ ! -f "$DIST" ]; then
  echo "BLOCK: DIST_ENTRY_MISSING"
  echo "Hint: CI/워크플로에서 dist가 생성되는 구조인지 확인하거나, 로컬 빌드 경로를 마련해야 합니다."
  exit 1
fi

# meta-only 요청(원문/프롬프트 없음)
MODEL_ID="${MODEL_ID:-demoA}"
INTENT="${INTENT:-ALGO_CORE_THREE_BLOCKS}"

node - <<'NODE' >"$OUT"
import fs from "node:fs";
import crypto from "node:crypto";

const dist = "webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js";
const mod = await import("file://" + process.cwd() + "/" + dist);

if (typeof mod.generateThreeBlocks !== "function") {
  console.log("# AI Smoke Result");
  console.log("- RESULT: BLOCK");
  console.log("- ERROR_CODE: ENTRYPOINT_NOT_FOUND");
  process.exit(1);
}

const req = {
  request_id: "smoke_" + Date.now(),
  intent: process.env.INTENT || "ALGO_CORE_THREE_BLOCKS",
  model_id: process.env.MODEL_ID || "demoA",
  device_class: "ondevice",
  client_version: "dev",
  ts_utc: new Date().toISOString(),
};

// latency
const t0 = process.hrtime.bigint();
const blocks = await mod.generateThreeBlocks(req);
const t1 = process.hrtime.bigint();
const latencyMs = Number(t1 - t0) / 1e6;

// pack meta only
const packMeta = blocks && blocks.__pack_meta ? blocks.__pack_meta : {};
const fp = String(packMeta.result_fingerprint_sha256 || "");
const packId = String(packMeta.pack_id || "");
const ver = String(packMeta.pack_version || "");
const man = String(packMeta.manifest_sha256 || "");
const computePath = String(packMeta.compute_path || "");

// meta-only fingerprint recheck (64 hex)
const fpOk = /^[0-9a-f]{64}$/.test(fp);

console.log("# AI Smoke Result");
console.log(`- DATE: ${new Date().toISOString()}`);
console.log(`- RESULT: OK`);
console.log(`- MODEL_ID: ${req.model_id}`);
console.log(`- INTENT: ${req.intent}`);
console.log(`- LATENCY_MS: ${Math.round(latencyMs * 1000) / 1000}`);
console.log(`- PACK_ID: ${packId}`);
console.log(`- PACK_VERSION: ${ver}`);
console.log(`- MANIFEST_SHA256_PRESENT: ${man ? 1 : 0}`);
console.log(`- FINGERPRINT_OK: ${fpOk ? 1 : 0}`);
console.log(`- COMPUTE_PATH: ${computePath || "na"}`);
NODE

echo "OK: wrote $OUT"
