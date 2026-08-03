import { sidecarFetch } from '../sidecarFetch';
import { nativeAuthorizedAccountingRequest } from './nativeAuthorizedRequest';
import {
  parseAssignment,
  parseAccountingReviewCapability,
  parsePage,
  parseQuarantinePage,
  parseProblem,
  parseRegistry,
  parseRules,
  parseSummary,
  type AssignmentResponse,
  type AssignmentScope,
  type ChartRegistryView,
  type LearnedRule,
  type ProblemDetail,
  type AccountingReviewCapabilityStatus,
  type UnaccountedPage,
  type ReviewSummary,
  type QuarantinedRow,
} from './contracts';

export class AccountingReviewApiError extends Error {
  constructor(readonly problem: ProblemDetail) {
    super(problem.safe_detail);
    this.name = 'AccountingReviewApiError';
  }
}

type Parser<T> = (value: unknown) => T;

async function request<T>(path: string, parser: Parser<T>, init: RequestInit = {}): Promise<T> {
  const response = await sidecarFetch(path, init);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error('ACCOUNTING_REVIEW_RESPONSE_NOT_JSON');
  }
  if (!response.ok) throw new AccountingReviewApiError(parseProblem(body, response.status));
  return parser(body);
}

async function privilegedRequest<T>(
  action: Parameters<typeof nativeAuthorizedAccountingRequest>[0],
  resourceType: string,
  resourceId: string,
  path: string,
  parser: Parser<T>,
  init: RequestInit,
): Promise<T> {
  const response = await nativeAuthorizedAccountingRequest(
    action, resourceType, resourceId, path, init,
  );
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error('ACCOUNTING_REVIEW_RESPONSE_NOT_JSON');
  }
  if (!response.ok) throw new AccountingReviewApiError(parseProblem(body, response.status));
  return parser(body);
}

function idempotencyKey(): string {
  if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== 'function') {
    throw new Error('SECURE_IDEMPOTENCY_SOURCE_UNAVAILABLE');
  }
  return globalThis.crypto.randomUUID();
}

export interface AssignmentIntent {
  idempotencyKey: string;
  clientActionId: string;
  userActionNonce: string;
}

export async function createAssignmentIntent(
  txnId: string,
  scope: AssignmentScope,
): Promise<AssignmentIntent> {
  const action = scope === 'SAME_VENDOR_FUTURE'
    ? 'RULE_FUTURE_CREATE'
    : 'ASSIGNMENT_CREATE';
  const nonce = await privilegedRequest(
    action, 'ACCOUNTING_TRANSACTION', txnId,
    `/v1/accounting/unaccounted/${encodeURIComponent(txnId)}/action-nonce?scope=${encodeURIComponent(scope)}`,
    value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('ACTION_NONCE_INVALID');
      const raw = value as Record<string, unknown>;
      const keys = Object.keys(raw).sort().join(',');
      if (keys !== ['action', 'expires_at_epoch_ms', 'schema_version', 'transaction_id', 'user_action_nonce'].sort().join(',')) throw new Error('ACTION_NONCE_UNKNOWN_FIELD');
      if (raw.schema_version !== '3.0' || raw.action !== action || raw.transaction_id !== txnId) throw new Error('ACTION_NONCE_BINDING_INVALID');
      if (typeof raw.user_action_nonce !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(raw.user_action_nonce)) throw new Error('ACTION_NONCE_INVALID');
      if (typeof raw.expires_at_epoch_ms !== 'number' || !Number.isSafeInteger(raw.expires_at_epoch_ms)) throw new Error('ACTION_NONCE_EXPIRY_INVALID');
      return raw.user_action_nonce;
    },
    { method: 'POST' },
  );
  if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== 'function') throw new Error('SECURE_IDEMPOTENCY_SOURCE_UNAVAILABLE');
  return {
    idempotencyKey: idempotencyKey(),
    clientActionId: globalThis.crypto.randomUUID(),
    userActionNonce: nonce,
  };
}

function ifMatch(version: number): string {
  if (!Number.isSafeInteger(version) || version < 1) throw new Error('RESOURCE_VERSION_INVALID');
  return `W/"${version}"`;
}

export function getAccountingReviewCapability(): Promise<AccountingReviewCapabilityStatus> {
  return request('/v1/accounting/review-capability', parseAccountingReviewCapability);
}

export function getReviewSummary(batchId: string): Promise<ReviewSummary> {
  return request(`/v1/accounting/batches/${encodeURIComponent(batchId)}/review-summary`, parseSummary);
}

export function getUnaccountedPage(batchId: string, cursor: string | null = null): Promise<UnaccountedPage> {
  const query = new URLSearchParams({ page_size: '50' });
  if (cursor) query.set('cursor', cursor);
  return request(`/v1/accounting/batches/${encodeURIComponent(batchId)}/unaccounted?${query}`, parsePage);
}

export function getQuarantinedRows(batchId: string): Promise<QuarantinedRow[]> {
  return request(
    `/v1/accounting/review/batches/${encodeURIComponent(batchId)}/quarantine`,
    parseQuarantinePage,
  );
}

export function recompileQuarantinedRow(input: {
  batchId: string;
  row: QuarantinedRow;
  amountMinor: number;
  bookedDate: string;
}): Promise<void> {
  if (!Number.isSafeInteger(input.amountMinor) || input.amountMinor === 0) {
    throw new Error('QUARANTINE_AMOUNT_INVALID');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.bookedDate)) throw new Error('QUARANTINE_DATE_INVALID');
  return privilegedRequest(
    'QUARANTINE_ROW_RECOMPILE', 'QUARANTINED_ROW', input.row.row_id,
    `/v1/accounting/review/batches/${encodeURIComponent(input.batchId)}/quarantine/${encodeURIComponent(input.row.row_id)}/recompile`,
    value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('QUARANTINE_RECOMPILE_INVALID');
      const raw = value as Record<string, unknown>;
      if (Object.keys(raw).sort().join(',') !== ['event_hash', 'resource_version', 'row_id', 'schema_version', 'state'].sort().join(',')) throw new Error('QUARANTINE_RECOMPILE_UNKNOWN_FIELD');
      if (raw.schema_version !== '3.0' || raw.state !== 'UNACCOUNTED' || raw.row_id !== input.row.row_id) throw new Error('QUARANTINE_RECOMPILE_BINDING_INVALID');
      if (typeof raw.event_hash !== 'string' || !/^[0-9a-f]{64}$/.test(raw.event_hash)) throw new Error('QUARANTINE_RECOMPILE_EVENT_INVALID');
      return undefined;
    },
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey(),
        'If-Match': ifMatch(input.row.resource_version),
      },
      body: JSON.stringify({ amount_minor: input.amountMinor, booked_date: input.bookedDate, currency: 'KRW' }),
    },
  );
}

export function getChartRegistry(registryDigest?: string): Promise<ChartRegistryView> {
  const query = new URLSearchParams({ locale: 'ko-KR' });
  if (registryDigest) query.set('registry_digest', registryDigest);
  return request(`/v1/accounting/chart-of-accounts?${query}`, parseRegistry);
}

export function assignAccount(input: {
  txnId: string;
  accountId: string;
  scope: AssignmentScope;
  transactionVersion: number;
  intent: AssignmentIntent;
}): Promise<AssignmentResponse> {
  const body = {
    account_id: input.accountId,
    scope: input.scope,
    client_action_id: input.intent.clientActionId,
    user_action_nonce: input.intent.userActionNonce,
    expected_transaction_version: input.transactionVersion,
  };
  return privilegedRequest(
    input.scope === 'SAME_VENDOR_FUTURE' ? 'RULE_FUTURE_CREATE' : 'ASSIGNMENT_CREATE',
    'ACCOUNTING_TRANSACTION', input.txnId,
    `/v1/accounting/unaccounted/${encodeURIComponent(input.txnId)}/assign`,
    parseAssignment,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': input.intent.idempotencyKey,
        'If-Match': ifMatch(input.transactionVersion),
      },
      body: JSON.stringify(body),
    },
  );
}

export function resolveRuleConflict(input: {
  conflictId: string;
  conflictVersion: number;
  decision: 'KEEP_EXISTING' | 'REPLACE_WITH_NEW';
}): Promise<AssignmentResponse> {
  return privilegedRequest(
    'CONFLICT_RESOLVE', 'RULE_CONFLICT', input.conflictId,
    `/v1/accounting/rule-conflicts/${encodeURIComponent(input.conflictId)}/resolve`,
    parseAssignment,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey(),
        'If-Match': ifMatch(input.conflictVersion),
      },
      body: JSON.stringify({
        schema_version: '2.0',
        decision: input.decision,
        expected_conflict_version: input.conflictVersion,
      }),
    },
  );
}

export function getLearnedRules(): Promise<LearnedRule[]> {
  return request('/v1/accounting/learned-rules', parseRules);
}

export async function deactivateLearnedRule(rule: LearnedRule): Promise<void> {
  await privilegedRequest(
    'RULE_DEACTIVATE', 'LEARNED_RULE', rule.rule_id,
    `/v1/accounting/learned-rules/${encodeURIComponent(rule.rule_id)}/deactivate`,
    value => value,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey(),
        'If-Match': ifMatch(rule.resource_version),
      },
    },
  );
}

export function revertRuleApplication(input: {
  txnId: string;
  transactionVersion: number;
}): Promise<{ txnId: string; transactionVersion: number }> {
  return privilegedRequest(
    'RULE_APPLICATION_REVERT', 'ACCOUNTING_TRANSACTION', input.txnId,
    `/v1/accounting/review/transactions/${encodeURIComponent(input.txnId)}/rule-application/revert`,
    value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('RULE_REVERT_RESPONSE_INVALID');
      const raw = value as Record<string, unknown>;
      const expected = ['event_hash', 'preserved_receipt_id', 'rule_id', 'schema_version', 'state', 'transaction_version', 'txn_id'];
      if (Object.keys(raw).sort().join(',') !== expected.sort().join(',')) throw new Error('RULE_REVERT_RESPONSE_UNKNOWN_FIELD');
      if (raw.schema_version !== '3.0' || raw.state !== 'UNACCOUNTED' || raw.txn_id !== input.txnId) throw new Error('RULE_REVERT_RESPONSE_BINDING_INVALID');
      if (typeof raw.transaction_version !== 'number' || !Number.isSafeInteger(raw.transaction_version)) throw new Error('RULE_REVERT_VERSION_INVALID');
      if (typeof raw.event_hash !== 'string' || !/^[0-9a-f]{64}$/.test(raw.event_hash)) throw new Error('RULE_REVERT_EVENT_INVALID');
      if (typeof raw.preserved_receipt_id !== 'string' || typeof raw.rule_id !== 'string') throw new Error('RULE_REVERT_RECEIPT_INVALID');
      return { txnId: input.txnId, transactionVersion: raw.transaction_version };
    },
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey(),
        'If-Match': ifMatch(input.transactionVersion),
      },
    },
  );
}
