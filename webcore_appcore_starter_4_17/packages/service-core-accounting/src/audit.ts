/**
 * 감사 로거
 * USE_PG=1이면 PostgreSQL에 저장, 아니면 콘솔에 기록
 * 
 * @module service-core-accounting/audit
 */

import { insertAudit, type AuditEvent } from '@appcore/data-pg';

export async function auditLog(ev: AuditEvent) {
  if (process.env.USE_PG === '1') {
    await insertAudit(ev);
  } else {
    // DEV/테스트: 콘솔 기록
    console.log(JSON.stringify({ level: 'audit', ...ev }));
  }
}

