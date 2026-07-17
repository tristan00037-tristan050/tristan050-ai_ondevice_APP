import { sidecarFetch } from '../sidecarFetch';
import {
  parseAssignment,
  parseAccountingReviewCapability,
  parsePage,
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

function idempotencyKey(): string {
  if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== 'function') {
    throw new Error('SECURE_IDEMPOTENCY_SOURCE_UNAVAILABLE');
  }
  return `intent:${globalThis.crypto.randomUUID()}`;
}

export function createAssignmentIntentKey(): string {
  return idempotencyKey();
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

export function getChartRegistry(registryDigest?: string): Promise<ChartRegistryView> {
  const query = new URLSearchParams({ locale: 'ko-KR' });
  if (registryDigest) query.set('registry_digest', registryDigest);
  return request(`/v1/accounting/chart-of-accounts?${query}`, parseRegistry);
}

export function assignAccount(input: {
  txnId: string;
  accountId: string;
  scope: AssignmentScope;
  registryDigest: string;
  transactionVersion: number;
  intentKey: string;
}): Promise<AssignmentResponse> {
  const body = {
    schema_version: '2.0',
    account_id: input.accountId,
    scope: input.scope,
    registry_digest: input.registryDigest,
    expected_transaction_version: input.transactionVersion,
  };
  return request(
    `/v1/accounting/unaccounted/${encodeURIComponent(input.txnId)}/assign`,
    parseAssignment,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': input.intentKey,
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
  return request(
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
  await request(
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
