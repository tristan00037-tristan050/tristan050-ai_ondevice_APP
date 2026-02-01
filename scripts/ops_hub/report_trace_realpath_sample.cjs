/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");
const os = require("os");
const { makeStore } = require("./trace_realpath_store_v1.cjs");

function fail(msg) {
  console.error(String(msg));
  process.exit(1);
}
function isPlainObject(x) {
  return !!x && typeof x === "object" && !Array.isArray(x);
}
function hasRawLike(s) {
  const v = String(s).toLowerCase();
  const banned = ["raw_text", "prompt", "messages", "document_body", "content", "private_key", "token=", "password=", "database_url="];
  return banned.some((k) => v.includes(k));
}
function makeId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

const ROOT = process.cwd();
const FIX = path.join(ROOT, "scripts/ops_hub/traceability_fixture.json");
if (!fs.existsSync(FIX)) fail(`missing fixture: ${FIX}`);

const data = JSON.parse(fs.readFileSync(FIX, "utf8"));
if (!isPlainObject(data) || !Array.isArray(data.events)) fail("BAD_FIXTURE_FORMAT");

// 임시 DB 경로(파일 기반). verify에서만 사용되고 커밋되지 않음.
const DB = path.join(os.tmpdir(), `ops_hub_trace_realpath_${Date.now()}_${Math.random().toString(16).slice(2)}.json`);
const store = makeStore(DB);

// fixture events -> realpath events( event_id/ts_utc/event_type 추가 )
let inserted = 0;
let duplicateNoop = 0;

for (const ev of data.events) {
  if (!isPlainObject(ev)) continue;
  const request_id = ev.request_id;
  if (typeof request_id !== "string" || request_id.length < 6) continue;

  const event_id = makeId("ev");
  const base = {
    v: 1,
    event_id,
    ts_utc: new Date().toISOString(),
    request_id,
    event_type: String(ev.event_type || "unknown"),
    trace: isPlainObject(ev.trace) ? ev.trace : {}
  };

  // 1) 첫 ingest
  const r1 = store.ingest(base);
  if (r1.inserted) inserted++;

  // 2) 같은 event_id로 한 번 더 ingest(멱등 체크)
  const r2 = store.ingest(base);
  if (!r2.inserted) duplicateNoop++;
}

// join rule: required trace fields(기존 traceability와 동일)
const required = [
  "ui_input_done_ms",
  "ui_render_done_ms",
  "runtime_algo_latency_ms",
  "runtime_manifest_sha256",
  "model_pack_id",
  "model_pack_version",
  "reason_code"
];

// request_id별로 trace merge(같은 request_id의 trace를 합친다)
function mergeTrace(evs) {
  let t = {};
  for (const e of evs) {
    if (isPlainObject(e.trace)) t = { ...t, ...e.trace };
  }
  return t;
}

const byReq = new Map();
for (const ev of data.events) {
  if (!isPlainObject(ev)) continue;
  const rid = ev.request_id;
  if (typeof rid !== "string" || rid.length < 6) continue;
  if (!byReq.has(rid)) byReq.set(rid, []);
  byReq.get(rid).push(ev);
}

const rows = [];
for (const [rid] of byReq.entries()) {
  const evsPersisted = store.listByRequestId(rid);
  const trace = mergeTrace(evsPersisted);

  const missing = required.filter((k) => !(k in trace));
  const joinable = missing.length === 0;

  rows.push({
    request_id: rid,
    joinable,
    missing,
    trace: joinable ? {
      ui_input_done_ms: trace.ui_input_done_ms,
      ui_render_done_ms: trace.ui_render_done_ms,
      runtime_algo_latency_ms: trace.runtime_algo_latency_ms,
      runtime_manifest_sha256: trace.runtime_manifest_sha256,
      model_pack_id: trace.model_pack_id,
      model_pack_version: trace.model_pack_version,
      reason_code: trace.reason_code
    } : {}
  });
}

// no-raw scan on produced output
const outJson = JSON.stringify({ report_type: "ops_hub_trace_realpath_v1", db: DB, rows }, null, 2);
if (hasRawLike(outJson)) fail("RAW_LIKE_CONTENT_DETECTED");

// output markers (no *_OK=1 here)
console.log(`persisted_inserted=${inserted}`);
console.log(`idempotent_noop=${duplicateNoop}`);
console.log(`joinable=true_count=${rows.filter(r => r.joinable).length}`);
for (const r of rows) {
  if (r.joinable) console.log(`JOIN_LINE request_id=${r.request_id} joinable=true`);
}
console.log(outJson);
process.exit(0);

