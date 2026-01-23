import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

function lockPath(name: string) {
  return path.join(DATA_DIR, `${name}.lock`);
}

function sleep(ms: number) {
  const end = Date.now() + ms;
  while (Date.now() < end) {}
}

/**
 * Multi-process safe-ish lock via exclusive create with retry.
 * - timeoutMs: total time to wait for lock
 * - retryMs: backoff between retries
 */
export function withFileLock<T>(
  name: string,
  fn: () => T,
  opts: { timeoutMs?: number; retryMs?: number } = {}
): T {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const lp = lockPath(name);

  const timeoutMs = opts.timeoutMs ?? 3000;
  const retryMs = opts.retryMs ?? 50;

  const start = Date.now();
  while (true) {
    try {
      const fd = fs.openSync(lp, "wx"); // exclusive
      try {
        return fn();
      } finally {
        fs.closeSync(fd);
        try { fs.unlinkSync(lp); } catch {}
      }
    } catch (e: any) {
      // lock exists → retry until timeout
      if (Date.now() - start >= timeoutMs) {
        throw new Error(`LOCK_TIMEOUT: ${name}`);
      }
      sleep(retryMs);
    }
  }
}
