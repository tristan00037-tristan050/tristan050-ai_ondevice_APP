#!/usr/bin/env node

import { BankSandboxAdapter } from '../packages/service-core-accounting/dist/adapters/BankSandboxAdapter.js';
import { safeSync } from '../packages/service-core-accounting/dist/reconciliation_sync.js';

const TENANTS = (process.env.TENANT_LIST || 'default').split(',');
const SOURCES = (process.env.SOURCES || 'bank-sbx').split(',');
const SINCE_DAYS = parseInt(process.env.SYNC_SINCE_DAYS || '7', 10);
const sinceISO = new Date(Date.now() - SINCE_DAYS * 24 * 3600 * 1000).toISOString();

for (const tenant of TENANTS) {
  for (const src of SOURCES) {
    if (src === 'bank-sbx') {
      const base = process.env.BANK_SBX_BASE;
      const token = process.env.BANK_SBX_TOKEN;
      if (!base || !token) {
        console.error(`❌ BANK_SBX_BASE or BANK_SBX_TOKEN not set for ${src}`);
        continue;
      }
      const ad = new BankSandboxAdapter(base, token);
      // 직렬 실행(레이트리밋 보호)
      /* eslint-disable no-await-in-loop */
      try {
        await safeSync(tenant, ad, sinceISO);
        console.log(`✅ Synced ${src} for tenant ${tenant}`);
      } catch (e) {
        const errMsg = e.message || String(e);
        if (errMsg.includes('fetch failed') || errMsg.includes('ECONNREFUSED')) {
          console.error(`❌ Sync failed for ${src} tenant ${tenant}: Connection failed`);
          console.error(`   Check if ${base} is accessible and BANK_SBX_TOKEN is valid`);
        } else {
          console.error(`❌ Sync failed for ${src} tenant ${tenant}:`, errMsg);
        }
      }
    }
  }
}
console.log('external sync done');

