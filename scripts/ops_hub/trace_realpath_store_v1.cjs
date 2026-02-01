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

// meta-only / no-raw guard (키/값 둘 다 검사)
function hasRawLikeAny(obj) {
  const banned = [
    "raw_text", "prompt", "messages", "document_body", "content",
    "private_key", "token=", "password=", "database_url="
  ];
  const maxStr = 300; // 너무 긴 문자열 차단(운영 원문 유입 방지)

  function walk(x, depth) {
    if (depth > 5) return true; // 과도한 깊이 차단
    if (x === null || x === undefined) return false;
    if (typeof x === "string") {
      const v = x.toLowerCase();
      if (x.length > maxStr) return true;
      return banned.some((k) => v.includes(k));
    }
    if (typeof x === "number" || typeof x === "boolean") return false;
    if (Array.isArray(x)) return true; // 배열 덤프 금지
    if (typeof x === "object") {
      for (const [k, v] of Object.entries(x)) {
        const kk = String(k).toLowerCase();
        if (banned.some((b) => kk.includes(b))) return true;
        if (walk(v, depth + 1)) return true;
      }
      return false;
    }
    return true;
  }
  return walk(obj, 0);
}

function makeStore(dbPath) {
  const state = loadJsonOrDefault(dbPath, { version: 1, events: [] });
  const seen = new Set(state.events.map((e) => e.event_id));

  function ingest(ev) {
    if (!ev || typeof ev !== "object") fail("BAD_EVENT");
    if (typeof ev.event_id !== "string" || ev.event_id.length < 8) fail("BAD_EVENT_ID");
    if (typeof ev.request_id !== "string" || ev.request_id.length < 6) fail("BAD_REQUEST_ID");
    if (hasRawLikeAny(ev)) fail("RAW_LIKE_EVENT_REJECTED");

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

