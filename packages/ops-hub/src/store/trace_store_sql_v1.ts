import Database from "better-sqlite3";
import { assertMetaOnly } from "../../../common/meta_only/validator_v1";

export type TraceStore = {
  ingest: (ev: unknown) => { inserted: boolean };
  listByRequestId: (requestId: string) => any[];
};

export function openTraceStore(dbPath: string): TraceStore {
  const db = new Database(dbPath);
  db.exec(`
    CREATE TABLE IF NOT EXISTS trace_events (
      event_id   TEXT PRIMARY KEY,
      request_id TEXT NOT NULL,
      payload    TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_trace_events_request_id ON trace_events(request_id);
  `);

  const insert = db.prepare(
    "INSERT OR IGNORE INTO trace_events(event_id, request_id, payload) VALUES (?, ?, ?)"
  );
  const byReq = db.prepare(
    "SELECT payload FROM trace_events WHERE request_id = ? ORDER BY event_id ASC"
  );

  function ingest(ev: any) {
    assertMetaOnly(ev);
    const eventId = String(ev.event_id ?? "");
    const requestId = String(ev.request_id ?? "");
    if (!eventId) throw new Error("EVENT_ID_MISSING");
    if (!requestId) throw new Error("REQUEST_ID_MISSING");
    const payload = JSON.stringify(ev);
    const info = insert.run(eventId, requestId, payload);
    return { inserted: info.changes === 1 };
  }

  function listByRequestId(requestId: string) {
    const rows = byReq.all(requestId);
    return rows.map((r: any) => JSON.parse(r.payload));
  }

  return { ingest, listByRequestId };
}

