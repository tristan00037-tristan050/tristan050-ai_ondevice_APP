const { mockTauriInvoke } = vi.hoisted(() => ({ mockTauriInvoke: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ invoke: mockTauriInvoke }));

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingReviewPage } from '../components/accounting_review/AccountingReviewPage';

const DIGEST = 'a'.repeat(64);
const OVERLAY = 'b'.repeat(64);
const TXN = 'txn_1234567890abcdef';

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

const capabilities = {
  schema_version: 'butler.accounting_capability_status.v2',
  capability_id: 'accounting.user_assignment',
  status: 'PARTIALLY_CONSUMED',
  registered: true,
  required_routes: 8,
  covered_routes: 8,
  self_test: 'PASS',
  reason_codes: ['INDEPENDENT_PRODUCT_E2E_REQUIRED'],
  verified_at: '2026-07-17T00:00:00Z',
  registry_digest: DIGEST,
  overlay_digest: OVERLAY,
  event_count: 0,
  evidence_digest: 'c'.repeat(64),
};

function summary(assigned = false) {
  return {
    schema_version: '2.0', batch_id: 'batch_1', batch_version: assigned ? 2 : 1,
    registry_digest: DIGEST, overlay_digest: OVERLAY,
    counts: {
      source_declared_valid: 0, auto_propose: assigned ? 0 : 1, user_rule_suggested: 0,
      review_required: 0, non_expense_bank_event: 0, user_assigned: assigned ? 1 : 0,
    },
    generated_at: '2026-07-16T00:00:00Z', evidence_digest: 'd'.repeat(64),
  };
}

function page(assigned = false) {
  return {
    schema_version: '2.0', batch_id: 'batch_1', batch_version: assigned ? 2 : 1,
    registry_digest: DIGEST, overlay_digest: OVERLAY,
    items: assigned ? [] : [{
      txn_id: TXN, transaction_version: 1, booked_date: '2026-07-01',
      money: { currency: 'KRW', minor_units: -12000 }, descriptor_display: '알•••점',
      display_policy: 'MASKED', bank_direction: 'OUTFLOW', review_state: 'AUTO_PROPOSE',
      suggestion: { account_id: 'acct_posting', source: 'AUTO_PROPOSE', safe_reason: '분류 결과를 제안합니다.', rule_id: null },
    }],
    total_count: assigned ? 0 : 1, next_cursor: null, etag: '"batch-1"',
  };
}

const registry = {
  schema_version: '2.0', registry_digest: DIGEST, overlay_digest: OVERLAY, locale: 'ko-KR', etag: '"registry"',
  entries: [
    { account_id: 'acct_group', account_code: null, display_name: '판매비 그룹', category_path: ['손익', '판매비'], node_kind: 'GROUP', assignable: false, disabled_reason: '집계용 계정', sort_order: 1 },
    { account_id: 'acct_posting', account_code: '811', display_name: '지급수수료', category_path: ['손익', '판매관리비', '지급수수료'], node_kind: 'POSTING', assignable: true, disabled_reason: null, sort_order: 2 },
  ],
};

describe('AccountingReviewPage product flow', () => {
  beforeEach(() => {
    mockTauriInvoke.mockReset();
    mockTauriInvoke.mockResolvedValue('test-capability-token');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uses the registry, defaults to THIS_ONLY, and sends one minimal idempotent assignment', async () => {
    let assigned = false;
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`)) {
        assigned = true;
        return jsonResponse({
          schema_version: '2.0', assignment_id: 'asg_1', txn_id: TXN,
          state: 'USER_ASSIGNED', account_id: 'acct_posting', scope: 'THIS_ONLY',
          rule_effect: 'NONE', rule_id: null, transaction_version: 2, receipt_digest: 'e'.repeat(64),
        });
      }
      if (url.includes('/review-summary')) return jsonResponse(summary(assigned));
      if (url.includes('/unaccounted')) return jsonResponse(page(assigned));
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    expect(await screen.findByRole('heading', { name: '계정 미확정 거래 검토' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '계정과목' })).toHaveValue('지급수수료');
    expect(screen.getByRole('radio', { name: '이번 거래만' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '같은 거래처의 다음 거래에도 제안' })).not.toBeChecked();

    const save = screen.getByRole('button', { name: '확인 후 저장' });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByText('검토할 거래가 없습니다.')).toBeInTheDocument());

    const mutations = requests.filter(request => request.url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`));
    expect(mutations).toHaveLength(1);
    const body = JSON.parse(String(mutations[0].init?.body));
    expect(body).toEqual({
      schema_version: '2.0', account_id: 'acct_posting', scope: 'THIS_ONLY',
      registry_digest: DIGEST, expected_transaction_version: 1,
    });
    expect(JSON.stringify(body)).not.toContain('descriptor');
    const headers = mutations[0].init?.headers as Record<string, string>;
    expect(headers['Idempotency-Key']).toMatch(/^intent:/);
    expect(headers['If-Match']).toBe('W/"1"');
  });

  it('exposes disabled registry nodes but never permits selecting them', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.includes('/review-summary')) return jsonResponse(summary());
      if (url.includes('/unaccounted')) return jsonResponse(page());
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));
    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    const input = await screen.findByRole('combobox', { name: '계정과목' });
    fireEvent.change(input, { target: { value: '판매비 그룹' } });
    const disabled = await screen.findByRole('option', { name: /판매비 그룹/ });
    expect(disabled).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(disabled);
    expect(input).toHaveValue('판매비 그룹');
    expect(screen.getByRole('button', { name: '확인 후 저장' })).toBeDisabled();
  });

  it('keeps the review list readable but mutations locked when capability self-test fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse({
        ...capabilities,
        status: 'UNAVAILABLE',
        self_test: 'FAIL',
        covered_routes: 4,
        reason_codes: ['REGISTRY_OVERLAY_UNAPPROVED'],
      });
      if (url.includes('/review-summary')) return jsonResponse(summary());
      if (url.includes('/unaccounted')) return jsonResponse(page());
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    expect(await screen.findByRole('heading', { name: '계정 미확정 거래 검토' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '확인 후 저장' })).toBeDisabled();
    expect(screen.getByText('저장 기능 상태를 확인할 수 없어 선택과 저장을 잠갔습니다.')).toBeInTheDocument();
  });

  it('does not overwrite a learned rule until the user resolves the 409 conflict', async () => {
    let assigned = false;
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`)) {
        return jsonResponse({
          type: 'https://butler.local/problems/accounting/learned_rule_conflict',
          title: '규칙 충돌', status: 409, code: 'LEARNED_RULE_CONFLICT', request_id: 'request_12345678',
          safe_detail: '기존 거래처 제안 규칙이 있습니다.', actions: ['KEEP_EXISTING', 'REPLACE_WITH_NEW'],
          current_version: 1, conflict_id: 'conflict_1', conflict_version: 1,
          existing_account_id: 'acct_group_old', proposed_account_id: 'acct_posting',
        }, 409);
      }
      if (url.endsWith('/v1/accounting/rule-conflicts/conflict_1/resolve')) {
        assigned = true;
        return jsonResponse({
          schema_version: '2.0', assignment_id: 'asg_2', txn_id: TXN,
          state: 'USER_ASSIGNED', account_id: 'acct_posting', scope: 'SAME_VENDOR_FUTURE',
          rule_effect: 'NONE', rule_id: null, transaction_version: 2, receipt_digest: 'f'.repeat(64),
        });
      }
      if (url.includes('/review-summary')) return jsonResponse(summary(assigned));
      if (url.includes('/unaccounted')) return jsonResponse(page(assigned));
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    await screen.findByRole('heading', { name: '계정 미확정 거래 검토' });
    fireEvent.click(screen.getByRole('radio', { name: '같은 거래처의 다음 거래에도 제안' }));
    fireEvent.click(screen.getByRole('button', { name: '확인 후 저장' }));
    expect(await screen.findByRole('alertdialog', { name: '기존 거래처 제안 규칙이 있습니다' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '기존 제안 유지' }));
    await waitFor(() => expect(screen.getByText('검토할 거래가 없습니다.')).toBeInTheDocument());

    const resolution = requests.find(request => request.url.endsWith('/v1/accounting/rule-conflicts/conflict_1/resolve'));
    expect(resolution).toBeDefined();
    expect(JSON.parse(String(resolution?.init?.body))).toEqual({
      schema_version: '2.0', decision: 'KEEP_EXISTING', expected_conflict_version: 1,
    });
    const headers = resolution?.init?.headers as Record<string, string>;
    expect(headers['If-Match']).toBe('W/"1"');
  });

  it('loads descriptor projections and deactivates a rule with the numeric resource ETag', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.includes('/review-summary')) return jsonResponse(summary());
      if (url.includes('/unaccounted')) return jsonResponse(page());
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      if (url.endsWith('/v1/accounting/learned-rules')) return jsonResponse({
        schema_version: '2.0',
        items: [{
          schema_version: '2.0', rule_id: 'rule_1234567890abcdef', account_id: 'acct_posting',
          source_assignment_id: 'asg_1234567890abcdef', state: 'ACTIVE_SUGGESTION',
          registry_digest: DIGEST, overlay_digest: OVERLAY, match_key_id: 'key-v1',
          normalization_version: 'vendor-v1', created_at: '2026-07-17T00:00:00Z',
          deactivated_at: null, resource_version: 3, descriptor_display: '알•••점',
        }],
      });
      if (url.endsWith('/v1/accounting/learned-rules/rule_1234567890abcdef/deactivate')) {
        return jsonResponse({ schema_version: '2.0', state: 'INACTIVE_USER' });
      }
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '거래처 제안 규칙 관리' }));
    expect(await screen.findByText('알•••점')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '비활성화' }));
    await screen.findByText('제안 규칙을 비활성화했습니다.');

    const mutation = requests.find(request => request.url.endsWith('/deactivate'));
    expect(mutation).toBeDefined();
    const headers = mutation?.init?.headers as Record<string, string>;
    expect(headers['If-Match']).toBe('W/"3"');
  });
});
