/* eslint-disable no-console */
/**
 * 대사(Reconciliation) E2E 테스트
 * 세션 생성 → 수동 매칭 → 조회
 * 
 * @module accounting_recon_e2e
 */

import crypto from 'node:crypto';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const TENANT_ID = process.env.TENANT_ID ?? 'default';
const API_KEY = process.env.API_KEY ?? 'collector-key:operator';

function bank(id, date, amt, cur, desc) {
  return { id, date, amount: amt, currency: cur, desc: desc };
}

function ledg(id, date, amt, cur, account, memo) {
  return { id, date, amount: amt, currency: cur, account, memo };
}

async function main() {
  const body = {
    bank: [
      bank('b1', '2025-11-03', '12500', 'KRW', '커피'),
      bank('b2', '2025-11-05', '320000', 'KRW', '임대료'),
    ],
    ledger: [
      ledg('l1', '2025-11-03', '12500', 'KRW', '8000', 'coffee'),
      ledg('l2', '2025-11-05', '320000', 'KRW', '5000', 'rent'),
    ],
    tolerance: { days: 3 },
  };

  // create session
  const r1 = await fetch(`${BFF_URL}/v1/accounting/reconciliation/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
    },
    body: JSON.stringify(body),
  });
  
  if (!r1.ok) {
    throw new Error(`create session failed: ${r1.status}`);
  }
  
  const s1 = await r1.json();
  if (!s1.sessionId || !Array.isArray(s1.matches)) {
    throw new Error('invalid session payload');
  }

  // manual match one pair
  const r2 = await fetch(`${BFF_URL}/v1/accounting/reconciliation/sessions/${s1.sessionId}/match`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': crypto.randomUUID(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
    },
    body: JSON.stringify({
      bank_id: 'b1',
      ledger_id: 'l1',
      client_request_id: crypto.randomUUID(),
    }),
  });
  
  if (!r2.ok) {
    throw new Error(`manual match failed: ${r2.status}`);
  }

  // get session
  const r3 = await fetch(`${BFF_URL}/v1/accounting/reconciliation/sessions/${s1.sessionId}`, {
    headers: {
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID,
    },
  });
  
  if (!r3.ok) {
    throw new Error(`get session failed: ${r3.status}`);
  }
  
  const s2 = await r3.json();
  const matched = s2.matches.find((m) => m.bank_id === 'b1' && m.ledger_id === 'l1');
  if (!matched) {
    throw new Error('expected manual match is missing');
  }
  
  console.log('✅ recon ok:', s2.sessionId, 'matches=', s2.matches.length);
}

main().catch((e) => {
  console.error('❌ E2E Reconciliation failed:', e);
  process.exit(1);
});


