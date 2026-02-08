/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");

function atomicWriteJson(filePath, obj) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = filePath + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
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

function openStore(dbPath) {
  const state = loadJsonOrDefault(dbPath, { version: 1, events: [] });
  const seen = new Set(state.events.map((e) => e.event_id));

  function ingest(ev) {
    assertMetaOnly(ev);
    const eventId = String(ev.event_id || "");
    const requestId = String(ev.request_id || "");
    if (!eventId) throw new Error("EVENT_ID_MISSING");
    if (!requestId) throw new Error("REQUEST_ID_MISSING");

    if (seen.has(eventId)) return { inserted: false };

    state.events.push(ev);
    seen.add(eventId);
    atomicWriteJson(dbPath, state);
    return { inserted: true };
  }

  function listByRequestId(requestId) {
    return state.events.filter((e) => e.request_id === requestId);
  }

  return { ingest, listByRequestId };
}

module.exports = { openStore };
