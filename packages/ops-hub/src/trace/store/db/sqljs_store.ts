/**
 * P1-PLAT-01: SQL.js Trace Store
 * 목적: sql.js 기반 trace 이벤트 저장소 (better-sqlite3 금지)
 * - UNIQUE/PK로 멱등 보장 (코드 if 금지)
 * - request_id 인덱스 생성
 */

// @ts-ignore - sql.js may not have complete type definitions
import initSqlJs from "sql.js";
import type { Database } from "sql.js";
import * as fs from "node:fs";
import * as path from "node:path";
import { validateTraceEventV1, type TraceEventV1 } from "../../schema/trace_event_v1";

// Global SQL.js module (initialized once, shared across instances)
let SQL_MODULE: any = null;
let SQL_INIT_PROMISE: Promise<any> | null = null;

async function getSQLModule(): Promise<any> {
  if (SQL_MODULE) return SQL_MODULE;
  if (!SQL_INIT_PROMISE) {
    SQL_INIT_PROMISE = initSqlJs().then((SQL: any) => {
      SQL_MODULE = SQL;
      return SQL;
    });
  }
  return SQL_INIT_PROMISE;
}

export type TraceStore = {
  ingest: (ev: unknown) => Promise<{ inserted: boolean }>;
  listByRequestId: (requestId: string) => Promise<TraceEventV1[]>;
  close: () => void;
};

export async function openTraceStore(dbPath: string): Promise<TraceStore> {
  const SQL = await getSQLModule();
  
  // Load existing DB or create new
  let db: Database;
  if (fs.existsSync(dbPath)) {
    const buffer = fs.readFileSync(dbPath);
    db = new SQL.Database(buffer);
  } else {
    db = new SQL.Database();
    // Ensure directory exists
    const dir = path.dirname(dbPath);
    if (dir) fs.mkdirSync(dir, { recursive: true });
  }

  // Create table with PRIMARY KEY (멱등 보장)
  db.run(`
    CREATE TABLE IF NOT EXISTS trace_events (
      event_id   TEXT PRIMARY KEY,
      request_id TEXT NOT NULL,
      ts_ms      INTEGER NOT NULL,
      kind       TEXT NOT NULL,
      payload    TEXT NOT NULL
    )
  `);

  // request_id 인덱스 생성 (DoD 요구사항)
  db.run(`
    CREATE INDEX IF NOT EXISTS idx_trace_events_request_id 
    ON trace_events(request_id)
  `);

  // Flush initial schema
  const data = db.export();
  fs.writeFileSync(dbPath, Buffer.from(data));

  async function ingest(ev: unknown): Promise<{ inserted: boolean }> {
    try {
      // 저장 전 검증 (trace_event_v1 파서로 먼저 검사) - 반드시 try 안
      const validated = validateTraceEventV1(ev);
      
      const payload = JSON.stringify(validated);
      
      // INSERT OR IGNORE로 멱등 보장 (DB UNIQUE/PK 사용, 코드 if 금지)
      db.run(
        "INSERT OR IGNORE INTO trace_events(event_id, request_id, ts_ms, kind, payload) VALUES (?, ?, ?, ?, ?)",
        [
          validated.event_id,
          validated.request_id,
          validated.ts_ms,
          validated.kind,
          payload,
        ]
      );
      
      // Flush to disk
      const data = db.export();
      fs.writeFileSync(dbPath, Buffer.from(data));
      
      // Check if inserted (changes > 0 means new row)
      const result = db.exec("SELECT changes() as changes");
      const changes = result.length > 0 && result[0].values?.[0]?.[0];
      const inserted = changes === 1;
      
      return { inserted };
    } catch (e: any) {
      // 외부로는 짧은 코드만 (e.message 노출 금지)
      // validation 실패 또는 DB 제약조건 위반 등
      const error = new Error("TRACE_STORE_INGEST_FAILED");
      (error as any).code = "TRACE_EVENT_INVALID";
      throw error;
    }
  }

  async function listByRequestId(requestId: string): Promise<TraceEventV1[]> {
    const result = db.exec(
      "SELECT payload FROM trace_events WHERE request_id = ? ORDER BY ts_ms ASC",
      [requestId]
    );
    
    if (result.length === 0) return [];
    
    const rows: TraceEventV1[] = [];
    for (const row of result[0].values || []) {
      const payloadStr = row[0] as string;
      try {
        const parsed = JSON.parse(payloadStr);
        rows.push(parsed as TraceEventV1);
      } catch (e) {
        // Skip invalid JSON
        continue;
      }
    }
    
    return rows;
  }

  function close() {
    db.close();
  }

  return { ingest, listByRequestId, close };
}

