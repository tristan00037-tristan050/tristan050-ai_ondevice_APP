import fs from "node:fs";
import path from "node:path";

type CounterName =
  | "LOCK_TIMEOUT"
  | "PERSIST_CORRUPTED"
  | "AUDIT_ROTATE"
  | "AUDIT_RETENTION_DELETE";

export type CounterEvent = {
  v: 1;
  event_id: string;     // idempotency key
  event_ts_ms: number;  // event time (NOT now)
  name: CounterName;
};

const DATA_DIR = path.resolve(__dirname, "../../../webcore_appcore_starter_4_17/backend/model_registry/data");
const FILE = path.join(DATA_DIR, "ops_counters_v2.json");

type Store = {
  // event_id seen within 24h window
  seen: Record<string, number>; // event_id -> event_ts_ms
  // per counter event timestamps
  buckets: Record<CounterName, number[]>;
};

function ensureDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function emptyStore(): Store {
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

function load(): Store {
  ensureDir();
  if (!fs.existsSync(FILE)) return emptyStore();
  try {
    return JSON.parse(fs.readFileSync(FILE, "utf8")) as Store;
  } catch {
    return emptyStore();
  }
}

function save(s: Store) {
  ensureDir();
  fs.writeFileSync(FILE, JSON.stringify(s, null, 2), "utf8");
}

function prune24h(s: Store, now_ms: number) {
  const cutoff = now_ms - 24 * 60 * 60 * 1000;
  for (const k of Object.keys(s.buckets) as CounterName[]) {
    s.buckets[k] = s.buckets[k].filter((t) => t >= cutoff);
  }
  for (const [eid, ts] of Object.entries(s.seen)) {
    if (ts < cutoff) delete s.seen[eid];
  }
}

export function bump(event: CounterEvent, now_ms = Date.now()): { bumped: boolean } {
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

export function readCounts24h(now_ms = Date.now()): Record<CounterName, number> {
  const s = load();
  prune24h(s, now_ms);
  const out: any = {};
  for (const k of Object.keys(s.buckets) as CounterName[]) out[k] = s.buckets[k].length;
  save(s);
  return out as Record<CounterName, number>;
}

