/* eslint-disable no-console */
/**
 * 퍼시스턴스 E2E 테스트
 * API 호출 후 DB에 실제로 적재되었는지 검증
 * 
 * @module persistence_db_e2e
 */

import crypto from 'node:crypto';
import { Pool } from 'pg';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const TENANT_ID = process.env.TENANT_ID ?? 'default';
const API_AUD = process.env.API_KEY_AUD ?? 'collector-key:auditor';
const API_OP = process.env.API_KEY_OP ?? 'collector-key:operator';
const DATABASE_URL = process.env.DATABASE_URL ?? 'postgres://app:app@localhost:5432/app';

async function must(ok, msg) {
  if (!ok) {
    throw new Error(msg);
  }
}

async function main() {
  const pg = new Pool({ connectionString: DATABASE_URL });

  // 1) Exports 생성 → export_jobs row 확인
  const r1 = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_AUD,
      'X-Tenant': TENANT_ID,
    },
    body: JSON.stringify({ since: '2025-11-01T00:00:00Z', limitDays: 7 }),
  });
  
  if (!r1.ok) {
    throw new Error(`exports create HTTP ${r1.status}`);
  }
  
  const j1 = await r1.json();
  const q1 = await pg.query('SELECT job_id FROM export_jobs WHERE job_id=$1', [j1.jobId]);
  await must(q1.rowCount === 1, 'export_jobs persisted');

  // 2) Reconciliation 세션 생성 → recon_sessions row 확인
  const body = {
    bank: [{ id: 'b1', date: '2025-11-03', amount: '1000', currency: 'KRW' }],
    ledger: [{ id: 'l1', date: '2025-11-03', amount: '1000', currency: 'KRW', account: '8000' }],
  };

  const r2 = await fetch(`${BFF_URL}/v1/accounting/reconciliation/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_OP,
      'X-Tenant': TENANT_ID,
    },
    body: JSON.stringify(body),
  });
  
  if (!r2.ok) {
    throw new Error(`recon create HTTP ${r2.status}`);
  }
  
  const s1 = await r2.json();
  const q2 = await pg.query('SELECT session_id FROM recon_sessions WHERE session_id=$1', [s1.sessionId]);
  await must(q2.rowCount === 1, 'recon_sessions persisted');

  console.log('✅ persistence ok: export_jobs & recon_sessions present');
  await pg.end();
}

main().catch((e) => {
  console.error('❌ persistence E2E failed:', e);
  process.exit(1);
});


