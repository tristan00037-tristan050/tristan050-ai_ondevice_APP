import { describe, it, expect, beforeEach } from "@jest/globals";
import fs from "node:fs";
import path from "node:path";
import { withFileLock } from "../services/file_lock";
import { appendAudit, AuditEvent } from "../services/audit";
import { persistReadJson, persistWriteJson } from "../services/persist_store";

describe("P1-4: file lock + audit rotation", () => {
  const dataDir = path.resolve(__dirname, "../data");
  const lockFile = path.join(dataDir, "test.lock");
  const auditFile = path.join(dataDir, "audit_log.json");
  const rotatedFile = path.join(dataDir, "audit_log.1.json");

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

  it("[EVID:AUDIT_LOG_ROTATE_OK] audit log rotates when exceeding max size", () => {
    // Create a large audit log (simulate by writing large data)
    const largeEvent: AuditEvent = {
      ts_ms: Date.now(),
      action: "APPLY",
      result: "ALLOW",
      sha256: "a".repeat(10000), // Large data to trigger rotation
    };

    // Fill audit log to exceed 1MB
    const events: AuditEvent[] = [];
    for (let i = 0; i < 150; i++) {
      events.push({ ...largeEvent, ts_ms: Date.now() + i });
    }
    
    // Write large audit log directly to trigger rotation
    persistWriteJson("audit_log.json", events);

    // Now append one more event - should trigger rotation
    appendAudit(largeEvent);

    // Check that rotated file exists
    expect(fs.existsSync(rotatedFile)).toBe(true);
    expect(fs.existsSync(auditFile)).toBe(true);

    // New audit log should be smaller (only 1 event)
    const newLog = persistReadJson<AuditEvent[]>("audit_log.json");
    expect(newLog).toBeTruthy();
    expect(newLog!.length).toBe(1);
  });
});

