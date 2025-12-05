import { ExternalLedgerAdapter } from './adapters/ExternalLedgerAdapter.js';
import {
  upsertTransactions,
  getOffset,
  setOffset,
} from '@appcore/data-pg';

// prom-client는 선택적 의존성 (메트릭이 활성화된 경우만 사용)
// 더미 메트릭 클래스
class DummyCounter {
  constructor() {}
  labels() {
    return { inc: () => {} };
  }
}

class DummyGauge {
  constructor() {}
  labels() {
    return { set: () => {} };
  }
}

let Counter: any = DummyCounter;
let Gauge: any = DummyGauge;
let metricsInitialized = false;

async function initMetrics() {
  if (metricsInitialized) return;
  try {
    const prom = await import('prom-client');
    Counter = prom.Counter;
    Gauge = prom.Gauge;
  } catch {
    // prom-client가 없으면 더미 메트릭 유지
    Counter = DummyCounter;
    Gauge = DummyGauge;
  }
  metricsInitialized = true;
}

// 메트릭 인스턴스는 lazy initialization
let syncErrors: any = null;
let syncLastTs: any = null;

function getSyncErrors() {
  if (!syncErrors) {
    syncErrors = new Counter({
      name: 'external_sync_errors_total',
      help: 'errors',
      labelNames: ['tenant', 'source'],
    });
  }
  return syncErrors;
}

function getSyncLastTs() {
  if (!syncLastTs) {
    syncLastTs = new Gauge({
      name: 'external_sync_last_ts',
      help: 'last ts',
      labelNames: ['tenant', 'source'],
    });
  }
  return syncLastTs;
}

export async function syncExternalLedger(
  tenant: string,
  adapter: ExternalLedgerAdapter,
  sinceISO?: string
) {
  if (!metricsInitialized) {
    await initMetrics();
  }

  let cursor = (await getOffset(tenant, adapter.source))?.last_cursor ?? undefined;
  let pages = 0,
    lastTs: string | null = null;

  while (true) {
    const { items, nextCursor } = await adapter.fetchTransactions({
      tenant,
      cursor,
      since: sinceISO,
      limit: 500,
    });
    if (items.length) {
      const rows = items.map((i) => ({
        external_id: i.id,
        ts: i.ts,
        amount: i.amount,
        currency: i.currency,
        merchant: i.merchant,
        memo: i.memo,
        account_id: i.account_id,
        raw: i.raw,
      }));
      await upsertTransactions(tenant, adapter.source, rows);
      lastTs = items[items.length - 1].ts;
      getSyncLastTs().labels(tenant, adapter.source).set(Date.parse(lastTs) / 1000);
    }
    pages++;
    cursor = nextCursor;
    if (!cursor || pages >= 100) break; // 안전 가드
  }
  await setOffset(tenant, adapter.source, cursor ?? null, lastTs);
}

export async function safeSync(
  tenant: string,
  adapter: ExternalLedgerAdapter,
  sinceISO?: string
) {
  try {
    await syncExternalLedger(tenant, adapter, sinceISO);
  } catch (e: any) {
    getSyncErrors().labels(tenant, adapter.source).inc();
    throw e;
  }
}

