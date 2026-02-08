/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");

function fail(msg) {
  console.error(String(msg));
  process.exit(1);
}

function atomicWriteJson(filePath, obj) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tmp = filePath + ".tmp";
  const data = JSON.stringify(obj, null, 2) + "\n";
  fs.writeFileSync(tmp, data, "utf8");
  // fsync(tmp)
  const fd = fs.openSync(tmp, "r+");
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  fs.renameSync(tmp, filePath);
}

function loadJsonOrDefault(filePath, def) {
  try {
    if (!fs.existsSync(filePath)) return def;
    const s = fs.readFileSync(filePath, "utf8");
    if (!s.trim()) return def;
    return JSON.parse(s);
  } catch {
    return def;
  }
}

// 단일 소스 validator 사용 (저장 전 검증)
const { assertMetaOnly } = require("../../packages/common/meta_only/validator_v1.cjs");

function makeStore(dbPath) {
  const state = loadJsonOrDefault(dbPath, { version: 1, events: [] });
  const seen = new Set(state.events.map((e) => e.event_id));

  function ingest(ev) {
    if (!ev || typeof ev !== "object") fail("BAD_EVENT");
    if (typeof ev.event_id !== "string" || ev.event_id.length < 8) fail("BAD_EVENT_ID");
    if (typeof ev.request_id !== "string" || ev.request_id.length < 6) fail("BAD_REQUEST_ID");
    
    // 단일 소스 validator 사용 (저장 전 검증, fail-closed)
    try {
      assertMetaOnly(ev);
    } catch (e) {
      fail(`RAW_LIKE_EVENT_REJECTED: ${e.message}`);
    }

    if (seen.has(ev.event_id)) {
      return { inserted: false }; // 멱등: 중복 저장 0
    }
    state.events.push(ev);
    seen.add(ev.event_id);
    atomicWriteJson(dbPath, state);
    return { inserted: true };
  }

  function listByRequestId(requestId) {
    return state.events.filter((e) => e.request_id === requestId);
  }

  function getStats() {
    return { events_total: state.events.length };
  }

  return { ingest, listByRequestId, getStats };
}

module.exports = { makeStore };

