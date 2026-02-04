/**
 * Export Audit Event V2 Tests
 * Verify that /api/v1/export/approve actually writes audit_event_v2 to file
 */

import express from "express";
import { exportApprove } from "../export_gate";
import { appendAuditEventV2 } from "../audit_event_v2_append";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

describe("Export Audit Event V2 (PROD-04b)", () => {
  const testAuditDir = path.join(os.tmpdir(), `os_audit_test_${Date.now()}`);
  const originalAuditDir = process.env.AUDIT_DIR;

  beforeAll(() => {
    process.env.AUDIT_DIR = testAuditDir;
  });

  afterAll(() => {
    if (originalAuditDir) {
      process.env.AUDIT_DIR = originalAuditDir;
    } else {
      delete process.env.AUDIT_DIR;
    }
    // Cleanup
    if (fs.existsSync(testAuditDir)) {
      fs.rmSync(testAuditDir, { recursive: true, force: true });
    }
  });

  beforeEach(() => {
    // Clear audit directory before each test
    if (fs.existsSync(testAuditDir)) {
      fs.rmSync(testAuditDir, { recursive: true, force: true });
    }
  });

  it("[EVID:EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK] approve writes audit_event_v2 to file", async () => {
    const body = {
      preview_token: "test_preview_token_123",
      payload: {
        status: "ready",
        request_id: "req_123",
        reason_code: "EXPORT_APPROVED"
      }
    };

    const result = exportApprove(body);
    expect(result.status).toBe(200);
    expect(result.json.ok).toBe(true);
    expect(result.json.export_id).toBeDefined();

    // Wait a bit for file write to complete
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Verify audit file exists
    const today = new Date().toISOString().split("T")[0];
    const auditFile = path.join(testAuditDir, `audit_${today}.json`);
    expect(fs.existsSync(auditFile)).toBe(true);

    // Verify audit file contains event
    const raw = fs.readFileSync(auditFile, "utf-8");
    const events = JSON.parse(raw);
    expect(Array.isArray(events)).toBe(true);
    expect(events.length).toBeGreaterThanOrEqual(1);

    // Verify event is meta-only (no long strings, no raw text)
    const event = events[events.length - 1];
    expect(event.ts_utc).toBeDefined();
    expect(event.export_id).toBeDefined();
    expect(event.outcome).toBe("APPROVED");
    expect(event.reason_code).toBeDefined();

    // Verify meta-only constraints
    for (const [key, value] of Object.entries(event)) {
      if (typeof value === "string") {
        expect(value.length).toBeLessThanOrEqual(120);
      }
      if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        // Nested objects should be shallow
        for (const [k, v] of Object.entries(value)) {
          if (typeof v === "string") {
            expect(v.length).toBeLessThanOrEqual(120);
          }
        }
      }
    }
  });

  it("appendAuditEventV2 writes to file atomically", async () => {
    const meta = {
      request_id: "req_atomic",
      action: "TEST",
      reason_code: "TEST_OK"
    };

    appendAuditEventV2(meta);

    await new Promise((resolve) => setTimeout(resolve, 100));

    const today = new Date().toISOString().split("T")[0];
    const auditFile = path.join(testAuditDir, `audit_${today}.json`);
    expect(fs.existsSync(auditFile)).toBe(true);

    const raw = fs.readFileSync(auditFile, "utf-8");
    const events = JSON.parse(raw);
    expect(events.length).toBe(1);
    expect(events[0].request_id).toBe("req_atomic");
  });
});

