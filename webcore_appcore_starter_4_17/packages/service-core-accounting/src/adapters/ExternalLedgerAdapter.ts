export type FetchParams = {
  tenant: string;
  since?: string;
  until?: string;
  cursor?: string;
  limit?: number;
};

export type ExternalTxn = {
  id: string;
  ts: string;
  amount: string;
  currency?: string;
  merchant?: string;
  memo?: string;
  account_id?: string;
  raw?: any;
};

export type FetchResult = {
  items: ExternalTxn[];
  nextCursor?: string;
  rateLimitResetAt?: string;
};

export interface ExternalLedgerAdapter {
  readonly source: string; // 'bank-sbx' | 'pg-sbx' | ...
  fetchTransactions(params: FetchParams): Promise<FetchResult>;
}

