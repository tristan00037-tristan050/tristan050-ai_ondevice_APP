import fs from "node:fs";
import path from "node:path";
import { persistReadJson, persistWriteJson } from "./persist_store";
import { bump } from "../../../../packages/common/src/metrics/counters";
import crypto from "node:crypto";

export type AuditEvent = {
  ts_ms: number;
  action: "DELIVERY" | "APPLY" | "ROLLBACK";
  result: "ALLOW" | "DENY";
  reason_code?: string;
  key_id?: string;
  sha256?: string;
};

const DATA_DIR = path.resolve(__dirname, "../data");
const MAX_BYTES = 1_000_000;
const RETAIN_DAYS = 14;

function dayKey(ts_ms: number) {
  return new Date(ts_ms).toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
}

function auditFile(day: string) {
  return `audit_${day}.json`;
}

function rotateIfNeeded(day: string) {
  const base = path.join(DATA_DIR, auditFile(day));
  if (!fs.existsSync(base)) return;
  const sz = fs.statSync(base).size;
  if (sz <= MAX_BYTES) return;
         const rotated = path.join(DATA_DIR, `audit_${day}.1.json`);
         try {
           fs.renameSync(base, rotated);
           const now = Date.now();
           const event_id = `${process.env.REPO_SHA || "unknown"}:AUDIT_ROTATE:${now}:${crypto.createHash("sha256").update(day + ":" + now).digest("hex").slice(0, 8)}`;
           bump({
             v: 1,
             event_id,
             event_ts_ms: now,
             name: "AUDIT_ROTATE",
           });
         } catch {}
}

function enforceRetention() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const files = fs.readdirSync(DATA_DIR).filter(f => f.startsWith("audit_") && f.endsWith(".json"));
  const cutoff = Date.now() - RETAIN_DAYS * 24 * 60 * 60 * 1000;
  for (const f of files) {
    const m = f.match(/^audit_(\d{4}-\d{2}-\d{2})/);
    if (!m) continue;
    const day = m[1];
    const ts = Date.parse(day + "T00:00:00.000Z");
    if (!Number.isFinite(ts)) continue;
           if (ts < cutoff) {
             try {
               fs.unlinkSync(path.join(DATA_DIR, f));
               const now = Date.now();
               const event_id = `${process.env.REPO_SHA || "unknown"}:AUDIT_RETENTION_DELETE:${now}:${crypto.createHash("sha256").update(f + ":" + now).digest("hex").slice(0, 8)}`;
               bump({
                 v: 1,
                 event_id,
                 event_ts_ms: now,
                 name: "AUDIT_RETENTION_DELETE",
               });
             } catch {}
           }
  }
}

export function appendAudit(evt: AuditEvent) {
  fs.mkdirSync(DATA_DIR, { recursive: true });

  const day = dayKey(evt.ts_ms);
  enforceRetention();
  rotateIfNeeded(day);

  const file = auditFile(day);
  const list = persistReadJson<AuditEvent[]>(file) ?? [];
  list.push(evt);

  // 민감 데이터(payload 원문)는 절대 저장하지 않는다(현재 타입에 없음)
  persistWriteJson(file, list);
}
