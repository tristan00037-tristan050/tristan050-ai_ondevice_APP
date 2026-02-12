import fs from "node:fs";
import readline from "node:readline";
import crypto from "node:crypto";

const DIST = "webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js";
const VEC = "ai/golden_vectors/v1.ndjson";

const BANNED_KEYS = new Set([
  "prompt","raw","messages","document_body",
  "request_id","ts_utc","nonce","manifest","run_id"
]);

function isFpOk(fp) {
  return /^[0-9a-f]{64}$/.test(String(fp || ""));
}

function validateMetaOnly(obj) {
  const maxDepth = 10;
  const maxStr = 200;
  const maxKeysPerObj = 50;
  let nodes = 0;
  const maxNodes = 20000;

  function walk(v, depth, path) {
    nodes++;
    if (nodes > maxNodes) throw new Error("GV_TOO_LARGE_V1");
    if (depth > maxDepth) throw new Error("GV_TOO_DEEP_V1");

    if (v === null) return;
    const t = typeof v;
    if (t === "string") {
      if (v.length > maxStr) throw new Error("GV_LONG_STRING_V1");
      return;
    }
    if (t === "number") {
      if (!Number.isFinite(v)) throw new Error("GV_NON_FINITE_NUMBER_V1");
      return;
    }
    if (t === "boolean") return;

    if (t === "object") {
      if (Array.isArray(v)) throw new Error("GV_ARRAY_FORBIDDEN_V1");

      const keys = Object.keys(v);
      if (keys.length > maxKeysPerObj) throw new Error("GV_TOO_MANY_KEYS_V1");

      for (const k of keys) {
        if (BANNED_KEYS.has(k)) throw new Error("GV_BANNED_KEY_V1");
        walk(v[k], depth + 1, `${path}.${k}`);
      }
      return;
    }
    throw new Error("GV_INVALID_TYPE_V1");
  }

  walk(obj, 0, "$");
  return true;
}

async function loadVectors() {
  if (!fs.existsSync(VEC)) throw new Error("GV_FILE_MISSING_V1");
  const rl = readline.createInterface({ input: fs.createReadStream(VEC), crlfDelay: Infinity });
  const out = [];
  for await (const line of rl) {
    const s = line.trim();
    if (!s) continue;
    const obj = JSON.parse(s);
    validateMetaOnly(obj);
    out.push(obj);
  }
  if (out.length < 5 || out.length > 10) throw new Error("GV_COUNT_OUT_OF_RANGE_V1");
  return out;
}

function cpuTimeMsV1() {
  const u = process.cpuUsage();
  const totalUs = (u.user || 0) + (u.system || 0);
  return totalUs / 1000.0;
}

async function call(mod, modelId, intent, vector, tag) {
  const mem0 = process.memoryUsage().rss / 1e6;
  const cpu0 = cpuTimeMsV1();
  const t0 = process.hrtime.bigint();

  const req = {
    request_id: `gv_${tag}_${Date.now()}`,
    intent,
    model_id: modelId,
    device_class: "ondevice",
    client_version: "dev",
    ts_utc: new Date().toISOString(),
    meta: vector, // meta-only payload
  };

  const blocks = await mod.generateThreeBlocks(req);

  const t1 = process.hrtime.bigint();
  const cpu1 = cpuTimeMsV1();
  const mem1 = process.memoryUsage().rss / 1e6;

  const packMeta = blocks && blocks.__pack_meta ? blocks.__pack_meta : {};
  const fp = String(packMeta.result_fingerprint_sha256 || "");
  const latencyMs = Number(t1 - t0) / 1e6;

  return {
    model_id: modelId,
    latency_ms: Math.round(latencyMs * 1000) / 1000,
    cpu_time_ms: Math.round((cpu1 - cpu0) * 1000) / 1000,
    mem_rss_mb: Math.round((mem1 - mem0) * 1000) / 1000,
    fingerprint_sha256: fp,
    fingerprint_ok: isFpOk(fp) ? 1 : 0,
    pack_id: String(packMeta.pack_id || ""),
    pack_version: String(packMeta.pack_version || ""),
  };
}

async function main() {
  if (!fs.existsSync(DIST)) throw new Error("GV_DIST_MISSING_V1");
  const mod = await import("file://" + process.cwd() + "/" + DIST);
  if (typeof mod.generateThreeBlocks !== "function") throw new Error("GV_ENTRYPOINT_MISSING_V1");

  const vectors = await loadVectors();
  const intent = process.env.INTENT || "ALGO_CORE_THREE_BLOCKS";
  const A = process.env.MODEL_A || "demoA";
  const B = process.env.MODEL_B || "demoB";

  const results = [];
  let d0OkAll = true;
  let packImpactAny = false;
  let budgetMeasuredAll = true;
  let rawOk = true;

  for (const v of vectors) {
    const caseId = v.case_id || "unknown";
    const a1 = await call(mod, A, intent, v, `${caseId}_a1`);
    const a2 = await call(mod, A, intent, v, `${caseId}_a2`);
    const b1 = await call(mod, B, intent, v, `${caseId}_b1`);

    const d0ok = (a1.fingerprint_ok === 1 && a2.fingerprint_ok === 1 && a1.fingerprint_sha256 === a2.fingerprint_sha256) ? 1 : 0;
    if (d0ok !== 1) d0OkAll = false;

    const impact = (a1.fingerprint_ok === 1 && b1.fingerprint_ok === 1 && a1.fingerprint_sha256 !== b1.fingerprint_sha256) ? 1 : 0;
    if (impact === 1) packImpactAny = true;

    const budgetOk =
      Number.isFinite(a1.latency_ms) && a1.latency_ms > 0 &&
      Number.isFinite(a1.cpu_time_ms) &&
      Number.isFinite(a1.mem_rss_mb);

    if (!budgetOk) budgetMeasuredAll = false;

    results.push({ case_id: caseId, A_a1: a1, A_a2: a2, B_b1: b1, d0_ok: d0ok, pack_impact_ok: impact });
  }

  const out = {
    date: new Date().toISOString(),
    intent,
    model_A: A,
    model_B: B,
    vectors_count: vectors.length,
    d0_stable_all: d0OkAll ? 1 : 0,
    pack_impact_any: packImpactAny ? 1 : 0,
    budget_measured_all: budgetMeasuredAll ? 1 : 0,
    results
  };

  fs.mkdirSync("ai/reports/latest", { recursive: true });
  fs.writeFileSync("ai/reports/latest/golden_vectors_v1.json", JSON.stringify(out, null, 2), "utf-8");

  console.log("GV_OUT_JSON=ai/reports/latest/golden_vectors_v1.json");
  console.log("GV_VECTORS_COUNT=" + vectors.length);
  console.log("GV_D0_STABLE_ALL=" + (out.d0_stable_all));
  console.log("GV_PACK_IMPACT_ANY=" + (out.pack_impact_any));
  console.log("GV_BUDGET_MEASURED_ALL=" + (out.budget_measured_all));
}

main().catch((e) => {
  console.log("ERROR_CODE=" + String(e && e.message ? e.message : "GV_UNKNOWN"));
  process.exit(1);
});

