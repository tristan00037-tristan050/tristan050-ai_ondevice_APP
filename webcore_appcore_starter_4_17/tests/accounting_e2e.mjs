#!/usr/bin/env node
/**
 * 회계 E2E 테스트
 * BFF API 실제 호출 테스트
 * 
 * @module accounting_e2e
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const BFF_URL = process.env.BFF_URL || 'http://localhost:8081';
const API_KEY = process.env.API_KEY || 'collector-key';
const TENANT = process.env.TENANT_ID || 'default';

function pickFirstSample(path) {
  const fullPath = path.startsWith('/') ? path : path.join(ROOT_DIR, path);
  const raw = fs.readFileSync(fullPath, 'utf8');
  const data = JSON.parse(raw);
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error('No golden samples found');
  }
  return data[0];
}

// 골든셋 포맷 가정:
// [{ "id": "sample-001", "policy_version": "appcore-6.0.0",
//    "input": { "line_items": [{ "description":"커피", "amount":"4500", "currency":"KRW" }] },
//    "ground_truth": { "postings": [{ "account":"비용:식대", "debit":"4500", "credit":"0", "currency":"KRW" }] } }]

try {
  const sample = pickFirstSample('datasets/gold/ledgers.json');

  // 골든셋이 기존 포맷인 경우 변환
  let lineItems;
  if (sample.input?.line_items) {
    lineItems = sample.input.line_items.map(item => ({
      desc: item.description || item.desc,
      amount: item.amount,
      currency: item.currency || 'KRW',
    }));
  } else if (sample.entries) {
    // 기존 포맷 (entries 기반)
    lineItems = sample.entries
      .filter(e => parseFloat(e.debit) > 0 || parseFloat(e.credit) > 0)
      .map(e => ({
        desc: e.note || 'Unknown',
        amount: parseFloat(e.debit) > 0 ? e.debit : e.credit,
        currency: sample.currency || 'KRW',
      }));
  } else {
    throw new Error('Invalid sample format: missing input.line_items or entries');
  }

  const reqBody = {
    policy_version: sample.policy_version || 'appcore-6.0.0',
    items: lineItems,
  };

  console.log(`🧪 E2E Test: POST ${BFF_URL}/v1/accounting/postings/suggest`);
  console.log(`Request:`, JSON.stringify(reqBody, null, 2));

  const res = await fetch(`${BFF_URL}/v1/accounting/postings/suggest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': API_KEY,
      'X-Tenant': TENANT,
      'Idempotency-Key': `e2e-${Date.now()}-${Math.random()}`,
    },
    body: JSON.stringify(reqBody),
  });

  if (res.status !== 200) {
    const err = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${err}`);
  }

  const json = await res.json();
  if (!json || !Array.isArray(json.postings) || json.postings.length === 0) {
    throw new Error('Invalid suggest response: missing postings');
  }

  // 간단 검증: 계정 코드가 존재하고 통화/금액 문자열이 존재하는지
  const p = json.postings[0];
  if (!p.account || !('debit' in p) || !('credit' in p)) {
    throw new Error('Invalid posting shape');
  }

  console.log('✅ E2E OK — /v1/accounting/postings/suggest returns postings.');
  console.log(`Response:`, JSON.stringify(json, null, 2));
  process.exit(0);
} catch (error) {
  console.error('❌ E2E Test Failed:', error.message);
  process.exit(1);
}
