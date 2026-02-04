import fs from "fs";

function block(msg) {
  console.error(`BLOCK: ${msg}`);
  process.exit(1);
}

function loadJson(p) {
  if (!fs.existsSync(p)) block(`missing file: ${p}`);
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { block(`invalid json: ${p}`); }
}

function main() {
  const [reqPath, outPath] = process.argv.slice(2);
  if (!reqPath || !outPath) block("usage: node generate_three_blocks.mjs <request.json> <out.json>");

  const t0 = process.hrtime.bigint();
  const req = loadJson(reqPath);

  // meta-only만 사용
  const meta = {
    request_id: String(req.request_id || ""),
    intent: String(req.intent || ""),
    model_id: String(req.model_id || ""),
    device_class: String(req.device_class || ""),
    client_version: String(req.client_version || ""),
    ts_utc: String(req.ts_utc || "")
  };
  if (!meta.request_id || !meta.intent || !meta.model_id) block("missing required meta fields");

  // 3블록 고정
  const out = {
    block_1_policy: {
      kind: "policy",
      meta,
      rules: [
        "meta-only input required",
        "no raw prompt/text/content accepted",
        "fail-closed on unknown keys"
      ]
    },
    block_2_plan: {
      kind: "plan",
      meta,
      steps: [
        "validate meta schema",
        "generate deterministic blocks",
        "emit signed manifest for artifacts"
      ]
    },
    block_3_checks: {
      kind: "checks",
      meta,
      checks: [
        "forbidden keys absent",
        "exactly 3 blocks present",
        "latency recorded for p95 gate"
      ]
    }
  };

  fs.writeFileSync(outPath, JSON.stringify(out, null, 2) + "\n", "utf8");

  const t1 = process.hrtime.bigint();
  const ms = Number(t1 - t0) / 1e6;
  console.log(`ALGO_LATENCY_MS=${ms.toFixed(3)}`);
  console.log(`OUT=${outPath}`);
}

main();
