import { spawnSync } from "node:child_process";
import fs from "node:fs";

function readPolicy() {
  const p = "docs/ops/contracts/PERF_REAL_PIPELINE_POLICY_V1.md";
  const s = fs.readFileSync(p, "utf8");
  const get = (k) => {
    const m = s.match(new RegExp(`^${k}=(\\d+)\\s*$`, "m"));
    return m ? Number(m[1]) : null;
  };
  return {
    MERGE_N: get("MERGE_N"),
    SCHEDULE_N: get("SCHEDULE_N"),
    MAX_STDDEV_MS: get("MAX_STDDEV_MS"),
    P95_BUDGET_MS: get("P95_BUDGET_MS"),
  };
}

function mean(xs) {
  return xs.reduce((a,b)=>a+b,0) / xs.length;
}
function stddev(xs) {
  const m = mean(xs);
  const v = xs.reduce((a,x)=>a+(x-m)*(x-m),0) / xs.length;
  return Math.sqrt(v);
}
function pctl(xs, p) {
  const ys = [...xs].sort((a,b)=>a-b);
  const idx = Math.min(ys.length-1, Math.max(0, Math.floor((p/100) * ys.length) - 1));
  return ys[idx];
}

const mode = process.env.PERF_RUN_MODE || "merge";
const policy = readPolicy();
const N = mode === "schedule" ? policy.SCHEDULE_N : policy.MERGE_N;

if (!Number.isFinite(N) || N < 3) {
  console.error(`BLOCK: bad sample size N=${N}`);
  process.exit(1);
}

const e2e = "webcore_appcore_starter_4_17/scripts/web_e2e/run_p95_marks_e2e.mjs";

const latencies = [];
const requestIds = [];

for (let i=0; i<N; i++) {
  const r = spawnSync("node", [e2e], { encoding: "utf8" });
  if (r.status !== 0) {
    console.error("BLOCK: e2e failed");
    console.error(r.stdout || "");
    console.error(r.stderr || "");
    process.exit(1);
  }

  // P95_MARKS_SUMMARY {"request_id":...,"runtime_latency_ms":...,"runtime_manifest_sha256":...}
  const m = (r.stdout || "").match(/^P95_MARKS_SUMMARY (.*)$/m);
  if (!m) {
    console.error("BLOCK: missing P95_MARKS_SUMMARY");
    process.exit(1);
  }
  const j = JSON.parse(m[1]);
  const rid = String(j.request_id || "");
  const lat = Number(j.runtime_latency_ms);
  if (!rid || !Number.isFinite(lat) || lat < 0) {
    console.error("BLOCK: bad summary fields");
    process.exit(1);
  }
  requestIds.push(rid);
  latencies.push(lat);
}

const out = {
  mode,
  N,
  mean_ms: Math.round(mean(latencies) * 1000) / 1000,
  stddev_ms: Math.round(stddev(latencies) * 1000) / 1000,
  p95_ms: pctl(latencies, 95),
  budget_ms: policy.P95_BUDGET_MS,
  max_stddev_ms: policy.MAX_STDDEV_MS,
  sample_request_id: requestIds[0],
};

console.log("REAL_PIPELINE_STATS " + JSON.stringify(out));
process.exit(0);

