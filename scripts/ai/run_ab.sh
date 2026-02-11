#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest

OUT_JSON="ai/reports/latest/ab.json"
OUT_MD="ai/reports/latest/ab_summary.md"

# A/B 모델팩 식별자 (현재 run_smoke.sh가 MODEL_ID를 받는 구조)
MODEL_A="${MODEL_A:-demoA}"
MODEL_B="${MODEL_B:-demoB}"
INTENT="${INTENT:-ALGO_CORE_THREE_BLOCKS}"

# dist 엔트리
DIST="webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js"
if [ ! -f "$DIST" ]; then
  echo "BLOCK: DIST_ENTRY_MISSING"
  exit 1
fi

node - <<'NODE' >"$OUT_MD"
import fs from "node:fs";

const dist = "webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js";
const mod = await import("file://" + process.cwd() + "/" + dist);

if (typeof mod.generateThreeBlocks !== "function") {
  console.log("# A/B Result");
  console.log("- RESULT: BLOCK");
  console.log("- ERROR_CODE: ENTRYPOINT_NOT_FOUND");
  process.exit(1);
}

function isFpOk(fp) {
  return /^[0-9a-f]{64}$/.test(String(fp || ""));
}

async function runOne(modelId) {
  const req = {
    request_id: "ab_" + modelId + "_" + Date.now(),
    intent: process.env.INTENT || "ALGO_CORE_THREE_BLOCKS",
    model_id: modelId,
    device_class: "ondevice",
    client_version: "dev",
    ts_utc: new Date().toISOString(),
  };

  const t0 = process.hrtime.bigint();
  const blocks = await mod.generateThreeBlocks(req);
  const t1 = process.hrtime.bigint();
  const latencyMs = Number(t1 - t0) / 1e6;

  const packMeta = blocks && blocks.__pack_meta ? blocks.__pack_meta : {};
  const fp = String(packMeta.result_fingerprint_sha256 || "");
  const packId = String(packMeta.pack_id || "");
  const ver = String(packMeta.pack_version || "");
  const man = String(packMeta.manifest_sha256 || "");

  return {
    model_id: modelId,
    intent: req.intent,
    latency_ms: Math.round(latencyMs * 1000) / 1000,
    pack_id: packId,
    pack_version: ver,
    manifest_sha256_present: man ? 1 : 0,
    fingerprint_sha256: fp,
    fingerprint_ok: isFpOk(fp) ? 1 : 0,
  };
}

const A = process.env.MODEL_A || "demoA";
const B = process.env.MODEL_B || "demoB";

const a = await runOne(A);
const b = await runOne(B);

const fpSame = (a.fingerprint_sha256 && b.fingerprint_sha256 && a.fingerprint_sha256 === b.fingerprint_sha256) ? 1 : 0;
const fpBothOk = (a.fingerprint_ok === 1 && b.fingerprint_ok === 1) ? 1 : 0;

const outJson = {
  date: new Date().toISOString(),
  intent: process.env.INTENT || "ALGO_CORE_THREE_BLOCKS",
  A: a,
  B: b,
  fingerprint_both_ok: fpBothOk,
  fingerprint_same: fpSame
};
fs.writeFileSync("ai/reports/latest/ab.json", JSON.stringify(outJson, null, 2), "utf-8");

console.log("# A/B Result");
console.log(`- DATE: ${outJson.date}`);
console.log(`- INTENT: ${outJson.intent}`);
console.log("");
console.log("## A");
console.log(`- MODEL_ID: ${a.model_id}`);
console.log(`- LATENCY_MS: ${a.latency_ms}`);
console.log(`- PACK_ID: ${a.pack_id}`);
console.log(`- PACK_VERSION: ${a.pack_version}`);
console.log(`- FINGERPRINT_OK: ${a.fingerprint_ok}`);
console.log("");
console.log("## B");
console.log(`- MODEL_ID: ${b.model_id}`);
console.log(`- LATENCY_MS: ${b.latency_ms}`);
console.log(`- PACK_ID: ${b.pack_id}`);
console.log(`- PACK_VERSION: ${b.pack_version}`);
console.log(`- FINGERPRINT_OK: ${b.fingerprint_ok}`);
console.log("");
console.log("## Compare");
console.log(`- FINGERPRINT_BOTH_OK: ${fpBothOk}`);
console.log(`- FINGERPRINT_SAME: ${fpSame}`);
console.log("");
console.log("Artifacts:");
console.log("- ai/reports/latest/ab_summary.md");
console.log("- ai/reports/latest/ab.json");
NODE

chmod +x scripts/ai/run_ab.sh

echo "OK: wrote $OUT_MD"
echo "OK: wrote $OUT_JSON"
