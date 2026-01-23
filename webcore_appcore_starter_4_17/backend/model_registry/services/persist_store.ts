import fs from "node:fs";
import path from "node:path";
import { withFileLock } from "./file_lock";

const DATA_DIR = path.resolve(__dirname, "../data");

function ensureDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

export function persistWriteJson(file: string, obj: unknown) {
  return withFileLock(file, () => {
    ensureDir();
    const p = path.join(DATA_DIR, file);
    const tmp = p + ".tmp";

    const data = JSON.stringify(obj, null, 2);

    // 1) write tmp (creates file if it doesn't exist)
    fs.writeFileSync(tmp, data, "utf8");

    // 2) fsync tmp (open file descriptor and sync to ensure data is written to disk)
    // Note: writeFileSync ensures file exists, but we check anyway for safety
    if (fs.existsSync(tmp)) {
      const fd = fs.openSync(tmp, "r+");
      try {
        fs.fsyncSync(fd);
      } finally {
        fs.closeSync(fd);
      }
    }

    // 3) rename tmp -> final (atomic replace)
    if (fs.existsSync(tmp)) {
      fs.renameSync(tmp, p);
    }
  });
}

export function persistReadJson<T>(file: string): T | null {
  return withFileLock(file, () => {
    ensureDir();
    const p = path.join(DATA_DIR, file);
    if (!fs.existsSync(p)) return null;

    const raw = fs.readFileSync(p, "utf8");
    try {
      return JSON.parse(raw) as T;
    } catch (e) {
      // fail-closed: corrupted persistence must not silently continue
      throw new Error(`PERSIST_CORRUPTED: ${file}`);
    }
  }, { timeoutMs: 3000, retryMs: 50 });
}

