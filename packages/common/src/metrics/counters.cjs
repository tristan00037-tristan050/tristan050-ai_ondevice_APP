const fs = require("node:fs");
const path = require("node:path");

const DATA_DIR = path.resolve(__dirname, "../../../webcore_appcore_starter_4_17/backend/model_registry/data");
const FILE = path.join(DATA_DIR, "ops_counters_v2.json");

function ensureDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function emptyStore() {
  return {
    seen: {},
    buckets: {
      LOCK_TIMEOUT: [],
      PERSIST_CORRUPTED: [],
      AUDIT_ROTATE: [],
      AUDIT_RETENTION_DELETE: [],
    },
  };
}

function load() {
  ensureDir();
  if (!fs.existsSync(FILE)) return emptyStore();
  try {
    return JSON.parse(fs.readFileSync(FILE, "utf8"));
  } catch {
    return emptyStore();
  }
}

function save(s) {
  ensureDir();
  fs.writeFileSync(FILE, JSON.stringify(s, null, 2), "utf8");
}

function prune24h(s, now_ms) {
  const cutoff = now_ms - 24 * 60 * 60 * 1000;
  for (const k of Object.keys(s.buckets)) {
    s.buckets[k] = s.buckets[k].filter((t) => t >= cutoff);
  }
  for (const [eid, ts] of Object.entries(s.seen)) {
    if (ts < cutoff) delete s.seen[eid];
  }
}

function bump(event, now_ms = Date.now()) {
  const s = load();
  prune24h(s, now_ms);

  // idempotency: same event_id => no double bump
  if (s.seen[event.event_id] !== undefined) {
    save(s);
    return { bumped: false };
  }

  // 24h window 기준은 event_ts_ms로 유지(흔들림 금지)
  s.seen[event.event_id] = event.event_ts_ms;
  s.buckets[event.name].push(event.event_ts_ms);

  save(s);
  return { bumped: true };
}

function readCounts24h(now_ms = Date.now()) {
  const s = load();
  prune24h(s, now_ms);
  const out = {};
  for (const k of Object.keys(s.buckets)) out[k] = s.buckets[k].length;
  save(s);
  return out;
}

module.exports = { bump, readCounts24h };

