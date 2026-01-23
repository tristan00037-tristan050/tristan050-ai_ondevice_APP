import { persistReadJson, persistWriteJson } from "./persist_store";

export type AuditEvent = {
  ts_ms: number;
  action: "DELIVERY" | "APPLY" | "ROLLBACK";
  result: "ALLOW" | "DENY";
  reason_code?: string;
  key_id?: string;
  sha256?: string;
};

const FILE = "audit_log.json";

export function appendAudit(evt: AuditEvent) {
  const list = persistReadJson<AuditEvent[]>(FILE) ?? [];
  list.push(evt);
  persistWriteJson(FILE, list);
}

