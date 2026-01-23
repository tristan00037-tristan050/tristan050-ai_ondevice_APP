import { describe, it, expect, beforeEach } from "@jest/globals";
import fs from "node:fs";
import path from "node:path";
import { withFileLock } from "../services/file_lock";
import { appendAudit, AuditEvent } from "../services/audit";
import { persistReadJson, persistWriteJson } from "../services/persist_store";

describe("P1-4: file lock + audit rotation", () => {
  const dataDir = path.resolve(__dirname, "../data");
  const lockFile = path.join(dataDir, "test.lock");
  const today = new Date().toISOString().slice(0, 10);
  const auditFile = path.join(dataDir, `audit_${today}.json`);
  const rotatedFile = path.join(dataDir, `audit_${today}.1.json`);

  beforeEach(() => {
    // Clean up test files
    if (fs.existsSync(lockFile)) fs.unlinkSync(lockFile);
    if (fs.existsSync(auditFile)) fs.unlinkSync(auditFile);
    if (fs.existsSync(rotatedFile)) fs.unlinkSync(rotatedFile);
  });

  it("[EVID:PERSIST_FILE_LOCK_OK] lock prevents concurrent access", () => {
    // First lock should succeed
    let firstLockAcquired = false;
    const firstLock = withFileLock("test", () => {
      firstLockAcquired = true;
      // Second lock should fail (file already exists)
      expect(() => {
        withFileLock("test", () => {
          // This should not execute
          expect(true).toBe(false);
        });
      }).toThrow();
    });
    expect(firstLockAcquired).toBe(true);
    expect(fs.existsSync(lockFile)).toBe(false); // Lock should be released
  });

  it("[EVID:LOCK_RETRY_TIMEOUT_OK] lock retries and times out correctly", () => {
    const lockFile = path.join(dataDir, "lock_retry_test.lock");
    if (fs.existsSync(lockFile)) fs.unlinkSync(lockFile);

    // Create a lock file manually to simulate another process holding the lock
    const fd = fs.openSync(lockFile, "wx");
    
    // Try to acquire lock with short timeout - should fail
    expect(() => {
      withFileLock("lock_retry_test", () => {
        // This should not execute
        expect(true).toBe(false);
      }, { timeoutMs: 100, retryMs: 10 });
    }).toThrow(/LOCK_TIMEOUT/);

    // Clean up
    fs.closeSync(fd);
    if (fs.existsSync(lockFile)) fs.unlinkSync(lockFile);
  });

  it("[EVID:AUDIT_DAILY_FILE_OK] audit log uses daily file format", () => {
    const today = new Date().toISOString().slice(0, 10);
    const auditFile = path.join(dataDir, `audit_${today}.json`);
    if (fs.existsSync(auditFile)) fs.unlinkSync(auditFile);

    const event: AuditEvent = {
      ts_ms: Date.now(),
      action: "APPLY",
      result: "ALLOW",
    };

    appendAudit(event);

    expect(fs.existsSync(auditFile)).toBe(true);
    const raw = fs.readFileSync(auditFile, "utf8");
    const events = JSON.parse(raw);
    expect(Array.isArray(events)).toBe(true);
    expect(events.length).toBeGreaterThan(0);
    expect(events[events.length - 1].action).toBe("APPLY");
  });

  it("[EVID:AUDIT_LOG_ROTATE_OK] audit log rotates when exceeding max size", () => {
    // Clean up any existing audit files for today
    if (fs.existsSync(auditFile)) fs.unlinkSync(auditFile);
    if (fs.existsSync(rotatedFile)) fs.unlinkSync(rotatedFile);

    // Create a large audit log (simulate by writing large data)
    const largeEvent: AuditEvent = {
      ts_ms: Date.now(),
      action: "APPLY",
      result: "ALLOW",
      sha256: "a".repeat(10000), // Large data to trigger rotation
    };

    // Fill audit log to exceed 1MB (need more events to exceed 1MB)
    const events: AuditEvent[] = [];
    for (let i = 0; i < 200; i++) {
      events.push({ ...largeEvent, ts_ms: Date.now() + i });
    }
    
    // Write large audit log directly to trigger rotation
    persistWriteJson(`audit_${today}.json`, events);

    // Wait a bit to ensure file is written
    const sleep = (ms: number) => {
      const end = Date.now() + ms;
      while (Date.now() < end) {}
    };
    sleep(100);

    // Now append one more event - should trigger rotation
    appendAudit(largeEvent);

    // Wait a bit for rotation to complete
    sleep(100);

    // Check that rotated file exists
    expect(fs.existsSync(rotatedFile)).toBe(true);
    expect(fs.existsSync(auditFile)).toBe(true);

    // New audit log should be smaller (only 1 event)
    const newLog = persistReadJson<AuditEvent[]>(`audit_${today}.json`);
    expect(newLog).toBeTruthy();
    expect(newLog!.length).toBe(1);
  });
});

