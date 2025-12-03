/* eslint-disable no-console */
/**
 * Approvals E2E 테스트
 * 
 * @module accounting_approvals_e2e
 */

import crypto from 'node:crypto';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const API_KEY = process.env.API_KEY ?? 'collector-key';
const TENANT_ID = process.env.TENANT_ID ?? 'default';

async function main() {
  const res = await fetch(`${BFF_URL}/v1/accounting/approvals/sample-id`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
    },
    body: JSON.stringify({
      action: 'approve',
      client_request_id: crypto.randomUUID(),
      note: 'ok'
    })
  });
  
  if (!res.ok) {
    const err = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${err}`);
  }
  
  const json = await res.json();
  console.log('approval ok:', json.status);
  console.log('✅ E2E Approvals test passed');
}

main().catch(e => {
  console.error('❌ E2E Approvals test failed:', e);
  process.exit(1);
});


