/* eslint-disable no-console */
/**
 * BFF Accounting E2E Smoke Test
 * POST /v1/accounting/postings/suggest 엔드포인트 검증
 * 
 * @module accounting_e2e_bff
 */

import crypto from 'node:crypto';

const BFF_URL = process.env.BFF_URL ?? 'http://localhost:8081';
const API_KEY = process.env.API_KEY ?? 'collector-key';
const TENANT_ID = process.env.TENANT_ID ?? 'default';

function uuid4() { return crypto.randomUUID(); }
function assert(c, m) { if (!c) throw new Error(m); }

async function main() {
  // 1) 헬스체크
  const health = await fetch(`${BFF_URL}/health`).then(r => r.json());
  console.log('[health]', health);
  assert(health?.status === 'ok', 'BFF health not ok');

  // 2) 샘플 요청 (desc/description 모두 허용)
  const reqBody = {
    client_request_id: uuid4(),
    policy_version: 'acct-0.1',
    currency: 'KRW',
    line_items: [
      { description: '커피 결제 스타벅스', amount: '4800' },
      { desc: '지하철 교통카드 충전', amount: '10000' }
    ]
  };

  const res = await fetch(`${BFF_URL}/v1/accounting/postings/suggest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': uuid4(),
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT_ID
    },
    body: JSON.stringify(reqBody)
  });
  console.log('[status]', res.status, res.statusText);
  assert(res.ok, `HTTP ${res.status}`);

  const data = await res.json();
  console.log('[body]', JSON.stringify(data, null, 2));
  assert(Array.isArray(data?.postings), 'postings must be an array');
  assert(typeof data?.rationale === 'string', 'rationale missing');
  assert(typeof data?.confidence === 'number' || typeof data?.confidence === 'string', 'confidence missing');

  console.log('✅ E2E BFF suggest smoke passed');
}

main().catch(err => { console.error('❌ E2E BFF suggest smoke failed:', err); process.exit(1); });


