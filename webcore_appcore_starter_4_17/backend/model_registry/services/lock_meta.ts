import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

export type LockMeta = {
  pid: number;
  host: string;
  created_at_utc: string;
  repo_sha: string;
};

export function lockMetaPath(name: string) {
  return path.join(DATA_DIR, `${name}.lock`);
}

export function writeLockMeta(name: string, meta: LockMeta) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(lockMetaPath(name), JSON.stringify(meta, null, 2), "utf8");
}

export function readLockMeta(name: string): LockMeta | null {
  const p = lockMetaPath(name);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as LockMeta;
  } catch {
    return null;
  }
}

export function removeLockMeta(name: string) {
  const p = lockMetaPath(name);
  if (fs.existsSync(p)) fs.unlinkSync(p);
}

