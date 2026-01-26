import fs from "node:fs";
import path from "node:path";

const AUDIT_DIR = process.env.AUDIT_DIR || "/tmp/os_audit";
const LOCK_TIMEOUT_MS = 5000;
const LOCK_RETRY_MS = 100;

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function withFileLock<T>(lockFile: string, fn: () => T): T {
  const start = Date.now();
  while (true) {
    try {
      const fd = fs.openSync(lockFile, "wx");
      fs.closeSync(fd);
      try {
        const result = fn();
        if (fs.existsSync(lockFile)) {
          fs.unlinkSync(lockFile);
        }
        return result;
      } catch (err) {
        if (fs.existsSync(lockFile)) {
          fs.unlinkSync(lockFile);
        }
        throw err;
      }
    } catch (err: any) {
      if (err.code === "EEXIST") {
        if (Date.now() - start > LOCK_TIMEOUT_MS) {
          throw new Error("LOCK_TIMEOUT");
        }
        // Synchronous sleep using busy-wait (simple approach for file locking)
        const sleepUntil = Date.now() + LOCK_RETRY_MS;
        while (Date.now() < sleepUntil) {
          // Busy wait
        }
        continue;
      }
      throw err;
    }
  }
}

function getAuditFileName(): string {
  const today = new Date().toISOString().split("T")[0];
  return `audit_${today}.json`;
}

function getAuditFilePath(): string {
  ensureDir(AUDIT_DIR);
  return path.join(AUDIT_DIR, getAuditFileName());
}

export function appendAuditEventV2(meta: Record<string, any>): void {
  const auditFile = getAuditFilePath();
  const lockFile = `${auditFile}.lock`;

  withFileLock(lockFile, () => {
    let events: any[] = [];
    if (fs.existsSync(auditFile)) {
      try {
        const raw = fs.readFileSync(auditFile, "utf-8");
        events = JSON.parse(raw);
        if (!Array.isArray(events)) {
          events = [];
        }
      } catch (err) {
        // Corrupted file, start fresh
        events = [];
      }
    }

    const event = {
      ts_utc: new Date().toISOString(),
      ...meta
    };

    events.push(event);

    const tmpFile = `${auditFile}.tmp`;
    fs.writeFileSync(tmpFile, JSON.stringify(events, null, 2), "utf-8");
    fs.fsyncSync(fs.openSync(tmpFile, "r+"));
    fs.renameSync(tmpFile, auditFile);
  });
}

