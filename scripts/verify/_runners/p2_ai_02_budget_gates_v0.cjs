/* meta-only runner: measures latency/mem/cpu_time_ms and enforces SSOT budgets */
const fs = require("fs");
const path = require("path");

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function fail(code) {
  process.stdout.write(`ERROR_CODE=${code}\n`);
  process.exit(1);
}

function nowNs() {
  return process.hrtime.bigint();
}

function cpuMsFromUsageDelta(us) {
  // cpuUsage returns microseconds
  const totalUs = (us.user || 0) + (us.system || 0);
  return Math.round(totalUs / 1000);
}

function mb(bytes) {
  return Math.round((bytes / (1024 * 1024)) * 100) / 100;
}

function stableNumber(n) {
  if (!Number.isFinite(n)) fail("MEASUREMENT_INVALID");
  return n;
}

function findRepoRoot() {
  // locate git root by walking up until .git exists
  let cur = process.cwd();
  for (let i = 0; i < 12; i++) {
    const g = path.join(cur, ".git");
    if (fs.existsSync(g)) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  fail("REPO_ROOT_NOT_FOUND");
}

(async () => {
  const root = findRepoRoot();

  // SSOT budgets
  const budgetsPath = path.join(root, "docs/ops/contracts/P2_AI_02_BUDGET_THRESHOLDS_V1.json");
  if (!fs.existsSync(budgetsPath)) fail("BUDGET_SSOT_MISSING");
  const budgets = readJson(budgetsPath);

  // energy proxy SSOT doc presence
  const energySsot = path.join(root, "docs/ops/contracts/P2_AI_02_ENERGY_PROXY_SSOT_V1.md");
  if (!fs.existsSync(energySsot)) fail("ENERGY_PROXY_SSOT_MISSING");

  // Call the same inference path used by P2-AI-01 (dist import).
  // This is CI-safe because workflow preflight builds dist.
  // If dist missing -> fail-closed.
  const distEntry = path.join(
    root,
    "webcore_appcore_starter_4_17/packages/bff-accounting/dist/lib/osAlgoCore.js"
  );
  if (!fs.existsSync(distEntry)) fail("DIST_ENTRY_MISSING");

  let mod;
  try {
    mod = await import("file://" + distEntry);
  } catch {
    fail("DIST_IMPORT_FAILED");
  }

  const generateThreeBlocks = mod && mod.generateThreeBlocks;
  if (typeof generateThreeBlocks !== "function") fail("ENTRYPOINT_NOT_FOUND");

  // Request: meta-only. No raw prompt.
  const req = {
    request_id: "p2-ai-02-budget",
    intent: "ALGO_CORE_THREE_BLOCKS",
    model_id: "demoA",            // use existing demo pack
    device_class: "web",
    client_version: "test",
    ts_utc: "2026-02-10T00:00:00Z"
  };

  const memBefore = process.memoryUsage();
  let memPeak = memBefore.heapUsed;
  const cpuBefore = process.cpuUsage();
  const t0 = nowNs();

  let resp;
  try {
    resp = await generateThreeBlocks(req);
  } catch (e) {
    // code-only
    const code = e && e.code ? String(e.code) : "INFER_THROWN";
    process.stdout.write(`ERROR_CODE=${code}\n`);
    process.exit(1);
  } finally {
    const memAfter = process.memoryUsage();
    memPeak = Math.max(memPeak, memAfter.heapUsed);
  }

  const t1 = nowNs();
  const cpuAfter = process.cpuUsage(cpuBefore);

  // Measurements (meta-only)
  const latencyMs = stableNumber(Number((t1 - t0)) / 1e6);
  const memPeakMb = stableNumber(mb(memPeak));
  const cpuTimeMs = stableNumber(cpuMsFromUsageDelta(cpuAfter)); // energy_proxy_v0=cpu_time_ms

  // Measurement presence: fail-closed
  if (!Number.isFinite(latencyMs) || !Number.isFinite(memPeakMb) || !Number.isFinite(cpuTimeMs)) {
    fail("MEASUREMENT_MISSING");
  }

  // Budget compare
  const latMax = Number(budgets.latency_ms_max);
  const memMax = Number(budgets.mem_peak_mb_max);
  const cpuMax = Number(budgets.cpu_time_ms_max);

  if (!Number.isFinite(latMax) || !Number.isFinite(memMax) || !Number.isFinite(cpuMax)) {
    fail("BUDGET_SSOT_INVALID");
  }

  if (latencyMs > latMax) fail("BUDGET_LATENCY_EXCEEDED");
  if (memPeakMb > memMax) fail("BUDGET_MEM_EXCEEDED");
  if (cpuTimeMs > cpuMax) fail("BUDGET_CPU_EXCEEDED");

  // Emit meta-only evidence
  process.stdout.write(`MEASURE_latency_ms=${latencyMs}\n`);
  process.stdout.write(`MEASURE_mem_peak_mb=${memPeakMb}\n`);
  process.stdout.write(`MEASURE_cpu_time_ms=${cpuTimeMs}\n`);
  process.stdout.write(`BUDGET_latency_ms_max=${latMax}\n`);
  process.stdout.write(`BUDGET_mem_peak_mb_max=${memMax}\n`);
  process.stdout.write(`BUDGET_cpu_time_ms_max=${cpuMax}\n`);

  process.exit(0);
})();

