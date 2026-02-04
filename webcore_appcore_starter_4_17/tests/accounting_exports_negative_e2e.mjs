/* eslint-disable no-console */
/**
 * Exports 부정 경로 E2E 테스트
 * 권한/요청오류/상한 위반 케이스 검증
 * 
 * @module accounting_exports_negative_e2e
 */

import crypto from 'node:crypto';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const TENANT_ID = process.env.TENANT_ID ?? 'default';

async function t(desc, fn) {
  try {
    await fn();
    console.log('✅', desc);
  } catch (e) {
    console.error('❌', desc, e.message || e);
    process.exitCode = 1;
  }
}

async function run() {
  // 1) Idempotency-Key 누락 → 400
  await t('missing Idempotency-Key → 400', async () => {
    const r = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Api-Key': 'collector-key:auditor',
        'X-Tenant': TENANT_ID
      },
      body: JSON.stringify({ limitDays: 30 })
    });
    if (r.status !== 400) {
      throw new Error(`expected 400, got ${r.status}`);
    }
  });

  // 2) viewer 권한 → 403
  await t('viewer → 403', async () => {
    const r = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        'X-Api-Key': 'collector-key:viewer',
        'X-Tenant': TENANT_ID
      },
      body: JSON.stringify({ limitDays: 30 })
    });
    if (r.status !== 403) {
      throw new Error(`expected 403, got ${r.status}`);
    }
  });

  // 3) limitDays > 90 → 422
  await t('limitDays > 90 → 422', async () => {
    const r = await fetch(`${BFF_URL}/v1/accounting/exports/reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        'X-Api-Key': 'collector-key:auditor',
        'X-Tenant': TENANT_ID
      },
      body: JSON.stringify({ limitDays: 120 })
    });
    if (r.status !== 422) {
      throw new Error(`expected 422, got ${r.status}`);
    }
  });

  console.log('✅ E2E Exports negative tests passed');
}

run().catch(e => {
  console.error('❌ E2E Exports negative tests failed:', e);
  process.exit(1);
});


