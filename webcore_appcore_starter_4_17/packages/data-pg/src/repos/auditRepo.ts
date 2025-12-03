/**
 * 감사 이벤트 리포지토리
 * 
 * @module data-pg/repos/auditRepo
 */

import { Pool } from 'pg';

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export type AuditEvent = {
  tenant: string;
  request_id?: string;
  idem_key?: string;
  actor?: string;
  ip?: string;
  route?: string;
  action: string;
  subject_type?: string;
  subject_id?: string;
  payload?: unknown;
};

export async function insertAudit(ev: AuditEvent): Promise<void> {
  await pool.query(
    `INSERT INTO accounting_audit_events
     (tenant, request_id, idem_key, actor, ip, route, action, subject_type, subject_id, payload)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
    [
      ev.tenant,
      ev.request_id ?? null,
      ev.idem_key ?? null,
      ev.actor ?? null,
      ev.ip ?? null,
      ev.route ?? null,
      ev.action,
      ev.subject_type ?? null,
      ev.subject_id ?? null,
      ev.payload ? JSON.stringify(ev.payload) : null,
    ],
  );
}

