/* eslint-disable no-console */
/**
 * Exports E2E 테스트
 * 
 * @module accounting_exports_e2e
 */

import crypto from 'node:crypto';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const API_KEY = process.env.API_KEY ?? 'collector-key';
const TENANT_ID = process.env.TENANT_ID ?? 'default';

async function main() {
  // 1. Export 잡 생성
  const r1 = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID
    },
    body: JSON.stringify({
      since: '2025-11-01T00:00:00Z',
      limitDays: 30
    })
  });
  
  if (!r1.ok) {
    const err = await r1.text().catch(() => '');
    throw new Error(`HTTP ${r1.status}: ${err}`);
  }
  
  const j1 = await r1.json();
  console.log('export job created:', j1.jobId);
  
  // 2. Export 잡 상태 조회
  const r2 = await fetch(`${BFF_URL}/v1/accounting/exports/${j1.jobId}`, {
    headers: {
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID
    }
  });
  
  if (!r2.ok) {
    const err = await r2.text().catch(() => '');
    throw new Error(`HTTP ${r2.status}: ${err}`);
  }
  
  const j2 = await r2.json();
  console.log('export job status:', j2.status);
  console.log('✅ E2E Exports test passed');
}

main().catch(e => {
  console.error('❌ E2E Exports test failed:', e);
  process.exit(1);
});


