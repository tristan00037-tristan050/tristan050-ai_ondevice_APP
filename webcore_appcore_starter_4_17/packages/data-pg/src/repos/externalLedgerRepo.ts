import { pool } from '../index.js';

export type ExternalTxn = {
  external_id: string;
  ts: string;
  amount: string;
  currency?: string;
  merchant?: string;
  memo?: string;
  account_id?: string;
  raw?: any;
};

export async function upsertTransactions(
  tenant: string,
  source: string,
  items: ExternalTxn[]
) {
  if (!items.length) return 0;
  const text = `
    INSERT INTO external_ledger
      (tenant, source, external_id, ts, amount, currency, merchant, account_id, memo, raw, updated_at)
    VALUES ${items
      .map(
        (_, i) =>
          `($1,$2,$${3 + i * 8},$${4 + i * 8},$${5 + i * 8},$${6 + i * 8},$${7 + i * 8},$${8 + i * 8},$${9 + i * 8},$${10 + i * 8}, NOW())`
      )
      .join(',')}
    ON CONFLICT (tenant,source,external_id)
    DO UPDATE SET ts=EXCLUDED.ts, amount=EXCLUDED.amount, currency=EXCLUDED.currency,
                  merchant=EXCLUDED.merchant, account_id=EXCLUDED.account_id, memo=EXCLUDED.memo,
                  raw=EXCLUDED.raw, updated_at=NOW();
  `;
  const args: any[] = [tenant, source];
  for (const it of items) {
    args.push(
      it.external_id,
      it.ts,
      it.amount,
      it.currency || 'KRW',
      it.merchant || null,
      it.account_id || null,
      it.memo || null,
      it.raw || null
    );
  }
  const r = await pool.query(text, args);
  return r.rowCount ?? 0;
}

export async function getOffset(tenant: string, source: string) {
  const r = await pool.query(
    `SELECT last_cursor, last_ts FROM external_ledger_offset WHERE tenant=$1 AND source=$2`,
    [tenant, source]
  );
  return r.rows[0] || null;
}

export async function setOffset(
  tenant: string,
  source: string,
  last_cursor: string | null,
  last_ts: string | null
) {
  await pool.query(
    `
    INSERT INTO external_ledger_offset (tenant,source,last_cursor,last_ts,updated_at)
    VALUES ($1,$2,$3,$4,NOW())
    ON CONFLICT (tenant,source) DO UPDATE SET last_cursor=EXCLUDED.last_cursor, last_ts=EXCLUDED.last_ts, updated_at=NOW()
  `,
    [tenant, source, last_cursor, last_ts]
  );
}

