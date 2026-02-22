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
  // OS 정책 브리지를 위한 헤더 추가 (Approvals 테스트와 동일 규칙)
  const userRole = API_KEY.includes(':') ? API_KEY.split(':')[1] : 'operator';

  // 1. Export 잡 생성
  const r1 = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
      'X-User-Role': userRole,
      'X-User-Id': 'test-user-1',
    },
    body: JSON.stringify({
      since: '2025-11-01T00:00:00Z',
      limitDays: 30
    })
  });
  
  if (!r1.ok) {
    const err = await r1.text().catch(() => '');
    if (r1.status === 500 && err.includes('missing_export_sign_secret')) {
      throw new Error(`HTTP ${r1.status}: ${err}\nHint: Start BFF with EXPORT_SIGN_SECRET (e.g. EXPORT_SIGN_SECRET=ci-secret or dev-export-secret).`);
    }
    throw new Error(`HTTP ${r1.status}: ${err}`);
  }
  
  const j1 = await r1.json();
  console.log('export job created:', j1.jobId);
  
  // 2. Export 잡 상태 조회
  const r2 = await fetch(`${BFF_URL}/v1/accounting/exports/${j1.jobId}`, {
    headers: {
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
      'X-User-Role': userRole,
      'X-User-Id': 'test-user-1',
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


