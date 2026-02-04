import fs from "node:fs";
import path from "node:path";
import { writeLockMeta, removeLockMeta } from "./lock_meta";
import { bump } from "../../../../packages/common/src/metrics/counters";
import crypto from "node:crypto";

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
               writeLockMeta(name, {
                 pid: process.pid,
                 host: process.env.HOSTNAME || "unknown",
                 created_at_utc: new Date().toISOString(),
                 repo_sha: process.env.REPO_SHA || "unknown",
               });
               return fn();
             } finally {
               fs.closeSync(fd);
               removeLockMeta(name);
             }
           } catch (e: any) {
             // lock exists → retry until timeout
             if (Date.now() - start >= timeoutMs) {
               const now = Date.now();
               const event_id = `${process.env.REPO_SHA || "unknown"}:LOCK_TIMEOUT:${now}:${crypto.createHash("sha256").update(name + ":" + now).digest("hex").slice(0, 8)}`;
               bump({
                 v: 1,
                 event_id,
                 event_ts_ms: now,
                 name: "LOCK_TIMEOUT",
               });
               throw new Error(`LOCK_TIMEOUT: ${name}`);
             }
      sleep(retryMs);
    }
  }
}
