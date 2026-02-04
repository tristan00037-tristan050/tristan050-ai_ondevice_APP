import { ExternalLedgerAdapter, FetchParams, FetchResult } from './ExternalLedgerAdapter.js';

export class BankSandboxAdapter implements ExternalLedgerAdapter {
  readonly source = 'bank-sbx';

  constructor(private base: string, private token: string) {}

  async fetchTransactions(p: FetchParams): Promise<FetchResult> {
    const url = new URL(`${this.base}/txns`);
    if (p.cursor) url.searchParams.set('cursor', p.cursor);
    if (p.since) url.searchParams.set('since', p.since);
    if (p.until) url.searchParams.set('until', p.until);
    if (p.limit) url.searchParams.set('limit', String(p.limit));

    const r = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    if (!r.ok) throw new Error(`bank-sbx ${r.status}`);
    const data = await r.json();
    return {
      items: (data.items || []).map((t: any) => ({
        id: String(t.id),
        ts: t.ts,
        amount: String(t.amount),
        currency: t.currency,
        merchant: t.merchant,
        memo: t.memo,
        account_id: t.account_id,
        raw: t,
      })),
      nextCursor: data.nextCursor,
    };
  }
}

