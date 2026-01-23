import { persistReadJson, persistWriteJson } from "./persist_store";
import fs from "node:fs";
import path from "node:path";

export type AuditEvent = {
  ts_ms: number;
  action: "DELIVERY" | "APPLY" | "ROLLBACK";
  result: "ALLOW" | "DENY";
  reason_code?: string;
  key_id?: string;
  sha256?: string;
};

const DATA_DIR = path.resolve(__dirname, "../data");
const FILE = "audit_log.json";
const MAX_SIZE_BYTES = 1024 * 1024; // 1MB

function rotateAuditLog() {
  const currentPath = path.join(DATA_DIR, FILE);
  if (!fs.existsSync(currentPath)) {
    return;
  }

  const stats = fs.statSync(currentPath);
  if (stats.size <= MAX_SIZE_BYTES) {
    return; // No rotation needed
  }

  // Rotate: move current to .1
  const rotatedPath = path.join(DATA_DIR, "audit_log.1.json");
  if (fs.existsSync(rotatedPath)) {
    fs.unlinkSync(rotatedPath); // Remove old rotated file
  }
  fs.renameSync(currentPath, rotatedPath);
}

export function appendAudit(evt: AuditEvent) {
  // Rotate if needed before appending
  rotateAuditLog();

  const list = persistReadJson<AuditEvent[]>(FILE) ?? [];
  list.push(evt);
  persistWriteJson(FILE, list);
}

