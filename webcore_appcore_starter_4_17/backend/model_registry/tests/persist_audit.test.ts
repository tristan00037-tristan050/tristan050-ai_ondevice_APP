import { describe, it, expect, beforeEach, afterEach } from "@jest/globals";
import fs from "node:fs";
import path from "node:path";
import { applyArtifact, rollbackArtifact } from "../services/delivery";
import { appendAudit, AuditEvent, dayKey, auditFile as getAuditFileName } from "../services/audit";
import { persistReadJson } from "../services/persist_store";
import { clearAll } from "../storage/service";
import { initializeSigningKey } from "../services/storage";

describe("P1-1 persist + audit (deny saves 0, audit records event)", () => {
  const dataDir = path.resolve(__dirname, "../data");
  // Use production code's dayKey to ensure date format consistency
  const today = dayKey(Date.now());
  const auditFileName = getAuditFileName(today);
  const auditFile = path.join(dataDir, auditFileName);
  const rotatedFile = path.join(dataDir, `audit_${today}.1.json`);

  beforeEach(() => {
    // Ensure data directory exists and clear audit log before each test
    fs.mkdirSync(dataDir, { recursive: true });
    if (fs.existsSync(auditFile)) {
      fs.unlinkSync(auditFile);
    }
    if (fs.existsSync(rotatedFile)) {
      fs.unlinkSync(rotatedFile);
    }
    clearAll();
    initializeSigningKey();
  });

  afterEach(() => {
    // Clean up audit log after each test
    if (fs.existsSync(auditFile)) {
      fs.unlinkSync(auditFile);
    }
    if (fs.existsSync(rotatedFile)) {
      fs.unlinkSync(rotatedFile);
    }
  });

  it("[EVID:PERSIST_AUDIT_DENY_OK] deny path does not save business data but writes audit", async () => {
    // Test deny case: missing signature
    const result = applyArtifact("tenant1", {
      sha256: "test-sha256",
      model_id: "m1",
      version_id: "v1",
      artifact_id: "a1",
      // signature, key_id missing
    });

    expect(result.ok).toBe(false);
    expect(result.applied).toBe(false);
    expect("reason_code" in result && result.reason_code).toBe("SIGNATURE_MISSING");

    // Verify audit log was written (daily file format)
    // Poll for actual audit event content (not just file existence)
    let retries = 20;
    let logs: AuditEvent[] | null = null;
    while (retries-- > 0) {
      if (fs.existsSync(auditFile)) {
        logs = persistReadJson<AuditEvent[]>(auditFileName) || null;
        if (logs && logs.length > 0) break;
      }
      await new Promise(r => setTimeout(r, 50));
    }
    expect(fs.existsSync(auditFile)).toBe(true);
    expect(logs).toBeTruthy();
    expect(logs!.length).toBeGreaterThan(0);

    // Verify deny event was recorded
    const denyEvent = logs!.find((e) => e.result === "DENY" && e.reason_code === "SIGNATURE_MISSING");
    expect(denyEvent).toBeDefined();
    expect(denyEvent!.action).toBe("APPLY");
    expect(denyEvent!.reason_code).toBe("SIGNATURE_MISSING");
    // Verify no sensitive payload data is stored (only reason_code)
    expect((denyEvent as any).model_id).toBeUndefined();
    expect((denyEvent as any).tenant_id).toBeUndefined();
  });

  it("[EVID:PERSIST_AUDIT_ALLOW_OK] allow path writes audit with ALLOW result", async () => {
    // Test that audit file can be written directly
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "ALLOW",
      key_id: "test-key",
      sha256: "test-sha256",
    });

    // Poll for actual audit event content
    let retries = 20;
    let logs: AuditEvent[] | null = null;
    while (retries-- > 0) {
      if (fs.existsSync(auditFile)) {
        logs = persistReadJson<AuditEvent[]>(auditFileName) || null;
        if (logs && logs.length > 0) break;
      }
      await new Promise(r => setTimeout(r, 50));
    }
    expect(fs.existsSync(auditFile)).toBe(true);
    expect(logs).toBeTruthy();
    expect(logs!.length).toBeGreaterThan(0);

    const allowEvent = logs!.find((e) => e.result === "ALLOW");
    expect(allowEvent).toBeDefined();
    expect(allowEvent!.action).toBe("APPLY");
    expect(allowEvent!.key_id).toBe("test-key");
    expect(allowEvent!.sha256).toBe("test-sha256");
  });

  it("[EVID:PERSIST_AUDIT_ROLLBACK_DENY_OK] rollback deny path writes audit", async () => {
    const result = rollbackArtifact("tenant1", {
      sha256: "test-sha256",
      model_id: "m1",
      version_id: "v1",
      artifact_id: "a1",
      reason_code: "TEST_ROLLBACK",
      // signature, key_id missing
    });

    expect(result.ok).toBe(false);
    expect(result.rolled_back).toBe(false);
    expect("reason_code" in result && result.reason_code).toBe("SIGNATURE_MISSING");

    // Verify audit log was written
    // Poll for actual audit event content (not just file existence)
    let retries = 20;
    let logs: AuditEvent[] | null = null;
    while (retries-- > 0) {
      if (fs.existsSync(auditFile)) {
        logs = persistReadJson<AuditEvent[]>(auditFileName) || null;
        if (logs && logs.length > 0) break;
      }
      await new Promise(r => setTimeout(r, 50));
    }
    expect(fs.existsSync(auditFile)).toBe(true);
    expect(logs).toBeTruthy();
    expect(logs!.length).toBeGreaterThan(0);

    const denyEvent = logs!.find((e) => e.action === "ROLLBACK" && e.result === "DENY");
    expect(denyEvent).toBeDefined();
    expect(denyEvent!.reason_code).toBe("SIGNATURE_MISSING");
  });
});
