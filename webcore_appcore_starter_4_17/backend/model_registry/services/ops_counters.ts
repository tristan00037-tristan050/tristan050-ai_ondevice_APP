import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");
const FILE = path.join(DATA_DIR, "ops_counters.json");

type CounterName =
  | "LOCK_TIMEOUT"
  | "PERSIST_CORRUPTED"
  | "AUDIT_ROTATE"
  | "AUDIT_RETENTION_DELETE";

type Store = Record<CounterName, number[]>; // ts_ms list

function ensureDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function load(): Store {
  ensureDir();
  if (!fs.existsSync(FILE)) {
    return {
      LOCK_TIMEOUT: [],
      PERSIST_CORRUPTED: [],
      AUDIT_ROTATE: [],
      AUDIT_RETENTION_DELETE: [],
    };
  }
  try {
    const raw = fs.readFileSync(FILE, "utf8");
    const obj = JSON.parse(raw) as Partial<Store>;
    return {
      LOCK_TIMEOUT: obj.LOCK_TIMEOUT ?? [],
      PERSIST_CORRUPTED: obj.PERSIST_CORRUPTED ?? [],
      AUDIT_ROTATE: obj.AUDIT_ROTATE ?? [],
      AUDIT_RETENTION_DELETE: obj.AUDIT_RETENTION_DELETE ?? [],
    };
  } catch {
    // fail-closed 성격이지만, 카운터 파일 손상은 운영 기능 자체를 죽이면 과도하므로 새로 시작
    return {
      LOCK_TIMEOUT: [],
      PERSIST_CORRUPTED: [],
      AUDIT_ROTATE: [],
      AUDIT_RETENTION_DELETE: [],
    };
  }
}

function save(s: Store) {
  ensureDir();
  fs.writeFileSync(FILE, JSON.stringify(s, null, 2), "utf8");
}

function prune24h(list: number[], now: number) {
  const cutoff = now - 24 * 60 * 60 * 1000;
  return list.filter((t) => t >= cutoff);
}

export function incCounter(name: CounterName, now_ms = Date.now()) {
  const s = load();
  // prune all
  for (const k of Object.keys(s) as CounterName[]) {
    s[k] = prune24h(s[k], now_ms);
  }
  s[name].push(now_ms);
  save(s);
}

export function readCounts24h(now_ms = Date.now()): Record<CounterName, number> {
  const s = load();
  const out: any = {};
  for (const k of Object.keys(s) as CounterName[]) {
    const pruned = prune24h(s[k], now_ms);
    out[k] = pruned.length;
  }
  return out as Record<CounterName, number>;
}

