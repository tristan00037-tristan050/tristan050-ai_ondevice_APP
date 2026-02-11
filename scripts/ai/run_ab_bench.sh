#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest
OUT_JSON="ai/reports/latest/ab_bench.json"
OUT_MD="ai/reports/latest/ab_bench.md"

MODEL_A="${MODEL_A:-demoA}"
MODEL_B="${MODEL_B:-demoB}"
INTENT="${INTENT:-ALGO_CORE_THREE_BLOCKS}"
RUNS="${RUNS:-20}"          # 반복 횟수
WARMUP="${WARMUP:-3}"       # 워밍업(측정 제외)

DIST="webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js"
if [ ! -f "$DIST" ]; then
  echo "BLOCK: DIST_ENTRY_MISSING"
  exit 1
fi

node - <<'NODE'
import fs from "node:fs";

const dist = "webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js";
const mod = await import("file://" + process.cwd() + "/" + dist);

if (typeof mod.generateThreeBlocks !== "function") {
  console.error("BLOCK: ENTRYPOINT_NOT_FOUND (generateThreeBlocks)");
  process.exit(1);
}

const MODEL_A = process.env.MODEL_A || "demoA";
const MODEL_B = process.env.MODEL_B || "demoB";
const INTENT = process.env.INTENT || "ALGO_CORE_THREE_BLOCKS";
const RUNS = Math.max(1, parseInt(process.env.RUNS || "20", 10));
const WARMUP = Math.max(0, parseInt(process.env.WARMUP || "3", 10));

function isFpOk(fp) {
  return /^[0-9a-f]{64}$/.test(String(fp || ""));
}

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const idx = Math.floor((p / 100) * (sorted.length - 1));
  return sorted[idx];
}

async function one(modelId) {
  const req = {
    request_id: "bench_" + modelId + "_" + Date.now() + "_" + Math.random().toString(16).slice(2),
    intent: INTENT,
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

  return {
    latency_ms: Math.round(latencyMs * 1000) / 1000,
    fingerprint_sha256: fp,
    fingerprint_ok: isFpOk(fp) ? 1 : 0,
    pack_id: packId,
    pack_version: ver,
  };
}

async function bench(modelId) {
  // warmup
  for (let i = 0; i < WARMUP; i++) {
    await one(modelId);
  }

  const samples = [];
  for (let i = 0; i < RUNS; i++) {
    samples.push(await one(modelId));
  }

  const lat = samples.map(s => s.latency_ms).slice().sort((a,b)=>a-b);
  const fps = samples.map(s => s.fingerprint_sha256);
  const fpOkAll = samples.every(s => s.fingerprint_ok === 1) ? 1 : 0;

  const fpSet = new Set(fps.filter(x => x));
  const fpStable = (fpSet.size === 1 && fpOkAll === 1) ? 1 : 0;

  // take first non-empty pack_id/version as representative
  const packId = samples.find(s => s.pack_id)?.pack_id || "";
  const packVer = samples.find(s => s.pack_version)?.pack_version || "";

  return {
    model_id: modelId,
    intent: INTENT,
    runs: RUNS,
    warmup: WARMUP,
    pack_id: packId,
    pack_version: packVer,
    latency_ms: {
      p50: percentile(lat, 50),
      p95: percentile(lat, 95),
      min: lat[0] || 0,
      max: lat[lat.length - 1] || 0
    },
    fingerprint_all_ok: fpOkAll,
    fingerprint_stable: fpStable,
    fingerprint_value: fpStable ? Array.from(fpSet)[0] : ""
  };
}

const A = await bench(MODEL_A);
const B = await bench(MODEL_B);

const fpBothStable = (A.fingerprint_stable === 1 && B.fingerprint_stable === 1) ? 1 : 0;
const fpSame = (fpBothStable === 1 && A.fingerprint_value && B.fingerprint_value && A.fingerprint_value === B.fingerprint_value) ? 1 : 0;

const out = {
  date: new Date().toISOString(),
  intent: INTENT,
  A,
  B,
  fingerprint_both_stable: fpBothStable,
  fingerprint_same: fpSame
};

fs.writeFileSync("ai/reports/latest/ab_bench.json", JSON.stringify(out, null, 2), "utf-8");

// markdown summary
let md = "";
md += "# A/B Bench Result\n";
md += `- DATE: ${out.date}\n`;
md += `- INTENT: ${INTENT}\n`;
md += `- RUNS: ${RUNS}\n`;
md += `- WARMUP: ${WARMUP}\n\n`;

md += "## A\n";
md += `- MODEL_ID: ${A.model_id}\n`;
md += `- PACK_ID: ${A.pack_id}\n`;
md += `- LATENCY_P50_MS: ${A.latency_ms.p50}\n`;
md += `- LATENCY_P95_MS: ${A.latency_ms.p95}\n`;
md += `- FP_ALL_OK: ${A.fingerprint_all_ok}\n`;
md += `- FP_STABLE: ${A.fingerprint_stable}\n\n`;

md += "## B\n";
md += `- MODEL_ID: ${B.model_id}\n`;
md += `- PACK_ID: ${B.pack_id}\n`;
md += `- LATENCY_P50_MS: ${B.latency_ms.p50}\n`;
md += `- LATENCY_P95_MS: ${B.latency_ms.p95}\n`;
md += `- FP_ALL_OK: ${B.fingerprint_all_ok}\n`;
md += `- FP_STABLE: ${B.fingerprint_stable}\n\n`;

md += "## Compare\n";
md += `- FINGERPRINT_BOTH_STABLE: ${fpBothStable}\n`;
md += `- FINGERPRINT_SAME: ${fpSame}\n`;

fs.writeFileSync("ai/reports/latest/ab_bench.md", md, "utf-8");
console.log("OK: wrote ai/reports/latest/ab_bench.json");
console.log("OK: wrote ai/reports/latest/ab_bench.md");
NODE
