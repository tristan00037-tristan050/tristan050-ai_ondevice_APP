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

// meta-only / no-raw 저장 전 차단(배열 금지, 깊이/길이 제한)
function assertMetaOnly(x, opts = { maxDepth: 4, maxString: 512, maxKeys: 64 }) {
  const bannedKeys = new Set([
    "raw_text","prompt","messages","document_body","input_text","output_text",
    "database_url","private_key","signing_key","seed"
  ]);
  const seen = new Set();

  function walk(v, depth) {
    if (depth > opts.maxDepth) throw new Error("META_ONLY_DEPTH");
    if (v === null || v === undefined) return;

    const t = typeof v;
    if (t === "string") {
      if (v.length > opts.maxString) throw new Error("META_ONLY_STRING_TOO_LONG");
      return;
    }
    if (t === "number" || t === "boolean") return;

    if (Array.isArray(v)) throw new Error("META_ONLY_ARRAY_FORBIDDEN");
    if (t !== "object") throw new Error("META_ONLY_INVALID_TYPE");
    if (seen.has(v)) throw new Error("META_ONLY_CYCLE");
    seen.add(v);

    const keys = Object.keys(v);
    if (keys.length > opts.maxKeys) throw new Error("META_ONLY_TOO_MANY_KEYS");
    for (const k of keys) {
      if (bannedKeys.has(k)) throw new Error("META_ONLY_BANNED_KEY");
      walk(v[k], depth + 1);
    }
  }

  if (typeof x !== "object" || x === null || Array.isArray(x)) throw new Error("META_ONLY_ROOT");
  walk(x, 0);
}

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

