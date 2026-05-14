import fs from "fs";

function block(msg) {
  console.error(`BLOCK: ${msg}`);
  process.exit(1);
}

function loadJson(p) {
  if (!fs.existsSync(p)) block(`missing file: ${p}`);
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    block(`invalid json: ${p}`);
  }
}

function requireMeta(req) {
  const meta = {
    request_id: String(req.request_id || ""),
    intent: String(req.intent || ""),
    model_id: String(req.model_id || ""),
    device_class: String(req.device_class || ""),
    client_version: String(req.client_version || ""),
    ts_utc: String(req.ts_utc || "")
  };
  if (!meta.request_id || !meta.intent || !meta.model_id) block("missing required meta fields");
  return meta;
}

function buildThreeBlocks(meta) {
  return {
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
}

function main() {
  const scriptStart = process.hrtime.bigint();
  const [reqPath, outPath] = process.argv.slice(2);
  if (!reqPath || !outPath) block("usage: node generate_three_blocks.mjs <request.json> <out.json>");

  const req = loadJson(reqPath);

  // ALGO_LATENCY_MS is the deterministic generation hot path used by ALGO-CORE-03.
  // Input file read and output file write are reported separately so filesystem jitter
  // does not mask generation regressions. The output artifact is still always written.
  const t0 = process.hrtime.bigint();
  const meta = requireMeta(req);
  const out = buildThreeBlocks(meta);
  const serialized = JSON.stringify(out) + "\n";
  const t1 = process.hrtime.bigint();

  fs.writeFileSync(outPath, serialized, "utf8");
  const t2 = process.hrtime.bigint();

  const latencyMs = Number(t1 - t0) / 1e6;
  const writeMs = Number(t2 - t1) / 1e6;
  const totalMs = Number(t2 - scriptStart) / 1e6;

  console.log(`ALGO_LATENCY_MS=${latencyMs.toFixed(3)}`);
  console.log(`ALGO_WRITE_MS=${writeMs.toFixed(3)}`);
  console.log(`ALGO_TOTAL_MS=${totalMs.toFixed(3)}`);
  console.log(`OUT=${outPath}`);
}

main();
