/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");

function isPlainObject(x) {
  return !!x && typeof x === "object" && !Array.isArray(x);
}

function fail(msg) {
  console.error(String(msg));
  process.exit(1);
}

function hasRawLike(s) {
  const v = String(s).toLowerCase();
  const banned = ["raw_text", "prompt", "messages", "document_body", "content", "private_key", "token=", "password="];
  return banned.some((k) => v.includes(k));
}

const ROOT = process.cwd();
const FIX = path.join(ROOT, "scripts/ops_hub/traceability_fixture.json");
if (!fs.existsSync(FIX)) fail(`missing fixture: ${FIX}`);

const data = JSON.parse(fs.readFileSync(FIX, "utf8"));
if (!isPlainObject(data) || !Array.isArray(data.events)) fail("BAD_FIXTURE_FORMAT");

const byReq = new Map();
for (const ev of data.events) {
  if (!isPlainObject(ev)) continue;
  const rid = ev.request_id;
  if (typeof rid !== "string" || rid.length < 6) continue;
  if (!byReq.has(rid)) byReq.set(rid, []);
  byReq.get(rid).push(ev);
}

// join rule: required trace fields
const required = [
  "ui_input_done_ms",
  "ui_render_done_ms",
  "runtime_algo_latency_ms",
  "runtime_manifest_sha256",
  "model_pack_id",
  "model_pack_version",
  "reason_code"
];

const rows = [];
for (const [rid, evs] of byReq.entries()) {
  const acc = { request_id: rid };
  let trace = {};
  for (const ev of evs) {
    if (isPlainObject(ev.trace)) trace = { ...trace, ...ev.trace };
  }

  const missing = required.filter((k) => !(k in trace));
  const joinable = missing.length === 0;

  // basic type checks (meta-only)
  if (joinable) {
    if (typeof trace.ui_input_done_ms !== "number" || typeof trace.ui_render_done_ms !== "number") {
      fail(`BAD_MARK_TYPES for ${rid}`);
    }
    if (trace.ui_render_done_ms < trace.ui_input_done_ms) {
      fail(`BAD_MARK_ORDER for ${rid}`);
    }
    if (typeof trace.runtime_algo_latency_ms !== "number") fail(`BAD_LATENCY_TYPE for ${rid}`);
    if (typeof trace.runtime_manifest_sha256 !== "string" || trace.runtime_manifest_sha256.length < 16) {
      fail(`BAD_MANIFEST_SHA for ${rid}`);
    }
    if (typeof trace.model_pack_id !== "string" || trace.model_pack_id.length < 3) fail(`BAD_PACK_ID for ${rid}`);
    if (typeof trace.model_pack_version !== "string" || trace.model_pack_version.length < 3) fail(`BAD_PACK_VER for ${rid}`);
    if (typeof trace.reason_code !== "string" || trace.reason_code.length < 3) fail(`BAD_REASON_CODE for ${rid}`);
  }

  const row = {
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
  };
  rows.push(row);
}

// no-raw scan on produced output
const outJson = JSON.stringify({ report_type: "ops_hub_traceability_v0_1", rows }, null, 2);
if (hasRawLike(outJson)) fail("RAW_LIKE_CONTENT_DETECTED");

// output markers (no *_OK=1 here)
console.log(`joinable=true_count=${rows.filter(r => r.joinable).length}`);
for (const r of rows) {
  if (r.joinable) {
    console.log(`JOIN_LINE request_id=${r.request_id} joinable=true`);
  }
}
console.log(outJson);
process.exit(0);

