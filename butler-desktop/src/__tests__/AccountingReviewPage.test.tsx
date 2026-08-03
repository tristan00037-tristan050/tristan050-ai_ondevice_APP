const { mockTauriInvoke } = vi.hoisted(() => ({ mockTauriInvoke: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ invoke: mockTauriInvoke }));

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingReviewPage } from '../components/accounting_review/AccountingReviewPage';

const DIGEST = 'a'.repeat(64);
const OVERLAY = 'b'.repeat(64);
const TXN = 'txn_1234567890abcdef';
const NONCE = 'n'.repeat(48);

interface NativeTestRequest {
  action: string;
  route_selector: string;
  resource_id: string;
  parent_resource_id: string | null;
  body_json: string | null;
  idempotency_key: string | null;
  if_match_version: number | null;
}

function nativePath(request: NativeTestRequest): string {
  const id = encodeURIComponent(request.resource_id);
  switch (request.route_selector) {
    case 'ACTION_NONCE_THIS_ONLY':
      return `/v1/accounting/unaccounted/${id}/action-nonce?scope=THIS_ONLY`;
    case 'ACTION_NONCE_FUTURE':
      return `/v1/accounting/unaccounted/${id}/action-nonce?scope=SAME_VENDOR_FUTURE`;
    case 'ASSIGNMENT_MUTATION':
      return `/v1/accounting/unaccounted/${id}/assign`;
    case 'RULE_DEACTIVATE':
      return `/v1/accounting/learned-rules/${id}/deactivate`;
    case 'RULE_APPLICATION_REVERT':
      return `/v1/accounting/review/transactions/${id}/rule-application/revert`;
    case 'QUARANTINE_ROW_RECOMPILE':
      if (!request.parent_resource_id) throw new Error('TEST_NATIVE_PARENT_REQUIRED');
      return `/v1/accounting/review/batches/${encodeURIComponent(request.parent_resource_id)}/quarantine/${id}/recompile`;
    case 'CONFLICT_RESOLVE':
      return `/v1/accounting/rule-conflicts/${id}/resolve`;
    default:
      throw new Error('TEST_NATIVE_ROUTE_UNEXPECTED');
  }
}

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
    schema_version: '3.0', batch_id: 'batch_1', batch_version: assigned ? 2 : 1,
    registry_digest: DIGEST, overlay_digest: OVERLAY,
    counts: {
      source_declared_valid: 0, auto_propose: assigned ? 0 : 1, user_rule_applied_draft: 0,
      review_required: 0, review_quarantine: 0, non_expense_bank_event: 0,
      user_assigned: assigned ? 1 : 0,
    },
    total_input_rows: 1,
    generated_at: '2026-07-16T00:00:00Z', evidence_digest: 'd'.repeat(64),
  };
}

function page(assigned = false) {
  return {
    schema_version: '3.0', batch_id: 'batch_1', batch_version: assigned ? 2 : 1,
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
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      value: {},
      configurable: true,
    });
    mockTauriInvoke.mockReset();
    mockTauriInvoke.mockImplementation(async (command: string, args?: {
      request?: NativeTestRequest;
    }) => {
      if (command === 'get_sidecar_capability_token') return 'test-capability-token';
      if (command !== 'box5_authorized_request' || !args?.request) {
        throw new Error(`UNEXPECTED_TAURI_COMMAND:${command}`);
      }
      const request = args.request;
      const headers: Record<string, string> = {};
      if (request.body_json !== null) headers['Content-Type'] = 'application/json';
      if (request.idempotency_key !== null) headers['Idempotency-Key'] = request.idempotency_key;
      if (request.if_match_version !== null) headers['If-Match'] = `W/"${request.if_match_version}"`;
      const response = await fetch(`http://127.0.0.1:8765${nativePath(request)}`, {
        method: 'POST',
        headers,
        body: request.body_json,
        redirect: 'error',
      });
      return {
        status: response.status,
        content_type: response.headers.get('Content-Type') ?? 'application/json',
        body: await response.text(),
      };
    });
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
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
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/action-nonce?scope=THIS_ONLY`)) return jsonResponse({
        schema_version: '3.0', transaction_id: TXN, action: 'ASSIGNMENT_CREATE',
        user_action_nonce: NONCE, expires_at_epoch_ms: 1_800_000_000_000,
      });
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`)) {
        assigned = true;
        return jsonResponse({
          schema_version: '3.0', assignment_id: 'asg_1', txn_id: TXN,
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
    expect(screen.getByRole('radio', { name: '같은 거래처의 다음 거래에 검토 초안 적용' })).not.toBeChecked();

    const save = screen.getByRole('button', { name: '확인 후 저장' });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByText('검토할 거래가 없습니다.')).toBeInTheDocument());

    const mutations = requests.filter(request => request.url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`));
    expect(mutations).toHaveLength(1);
    const body = JSON.parse(String(mutations[0].init?.body));
    expect(body.account_id).toBe('acct_posting');
    expect(body.scope).toBe('THIS_ONLY');
    expect(body.expected_transaction_version).toBe(1);
    expect(body.user_action_nonce).toBe(NONCE);
    expect(body.client_action_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(Object.keys(body).sort()).toEqual([
      'account_id', 'client_action_id', 'expected_transaction_version', 'scope', 'user_action_nonce',
    ]);
    expect(JSON.stringify(body)).not.toContain('descriptor');
    const headers = mutations[0].init?.headers as Record<string, string>;
    expect(headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers['If-Match']).toBe('W/"1"');
    expect(requests.some(request => request.url.endsWith(
      `/v1/accounting/unaccounted/${TXN}/action-nonce?scope=THIS_ONLY`,
    ))).toBe(true);
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

  it('fails closed before protected accounting data loads when capability self-test fails', async () => {
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
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
    expect(await screen.findByRole('alert')).toHaveTextContent('계정 검토 제품 게이트가 준비되지 않아 읽기와 저장을 잠갔습니다.');
    expect(screen.queryByRole('heading', { name: '계정 미확정 거래 검토' })).not.toBeInTheDocument();
    expect(requests).toEqual([expect.stringMatching(/\/v1\/accounting\/review-capability$/)]);
  });

  it('explains authority unavailability and never requests protected accounting data', async () => {
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse({
        ...capabilities,
        status: 'UNAVAILABLE',
        self_test: 'FAIL',
        reason_codes: ['AUTHORITY_UNAVAILABLE'],
      });
      throw new Error(`PROTECTED_REQUEST_MUST_NOT_RUN:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '승인된 사용자 권한 authority를 확인할 수 없어 회계 검토와 저장을 잠갔습니다.',
    );
    expect(screen.getByRole('button', { name: '권한 다시 확인' })).toBeInTheDocument();
    expect(requests).toEqual([expect.stringMatching(/\/v1\/accounting\/review-capability$/)]);
  });

  it('does not overwrite a learned rule until the user resolves the 409 conflict', async () => {
    let assigned = false;
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/action-nonce?scope=SAME_VENDOR_FUTURE`)) return jsonResponse({
        schema_version: '3.0', transaction_id: TXN, action: 'RULE_FUTURE_CREATE',
        user_action_nonce: NONCE, expires_at_epoch_ms: 1_800_000_000_000,
      });
      if (url.endsWith(`/v1/accounting/unaccounted/${TXN}/assign`)) {
        return jsonResponse({
          type: 'https://butler.local/problems/accounting/learned_rule_conflict',
          title: '규칙 충돌', status: 409, code: 'RULE_CONFLICT_REVIEW_REQUIRED',
          reason_code: 'RULE_CONFLICT_REVIEW_REQUIRED', request_id: 'request_12345678',
          safe_detail: '기존 거래처 제안 규칙이 있습니다.', actions: ['KEEP_EXISTING', 'REPLACE_WITH_NEW'],
          detail: '기존 거래처 제안 규칙이 있습니다.',
          current_version: 1, conflict_id: 'conflict_1', conflict_version: 1,
          existing_account_id: 'acct_group_old', proposed_account_id: 'acct_posting',
        }, 409);
      }
      if (url.endsWith('/v1/accounting/rule-conflicts/conflict_1/resolve')) {
        assigned = true;
        return jsonResponse({
          schema_version: '3.0', assignment_id: 'asg_2', txn_id: TXN,
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
    fireEvent.click(screen.getByRole('radio', { name: '같은 거래처의 다음 거래에 검토 초안 적용' }));
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
        schema_version: '3.0',
        items: [{
          schema_version: '3.0', rule_id: 'rule_1234567890abcdef', account_id: 'acct_posting',
          source_assignment_id: 'asg_1234567890abcdef', state: 'ACTIVE_USER_RULE',
          registry_digest: DIGEST, overlay_digest: OVERLAY, match_key_id: 'key-v1',
          normalization_version: 'vendor-v1', adapter_id: 'kr.ibk.statement',
          adapter_version: '1.0.0', direction: 'OUT', currency: 'KRW',
          created_at: '2026-07-17T00:00:00Z',
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

  it('reverts only the current auto-applied draft and keeps the immutable receipt', async () => {
    let reverted = false;
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.includes('/review-summary')) return jsonResponse({
        ...summary(),
        counts: {
          ...summary().counts,
          auto_propose: 0,
          user_rule_applied_draft: reverted ? 0 : 1,
          review_required: reverted ? 1 : 0,
        },
        batch_version: reverted ? 2 : 1,
      });
      if (url.includes('/unaccounted')) return jsonResponse({
        ...page(),
        batch_version: reverted ? 2 : 1,
        items: [{
          ...page().items[0],
          transaction_version: reverted ? 2 : 1,
          review_state: reverted ? 'REVIEW_REQUIRED' : 'USER_RULE_APPLIED_DRAFT',
          suggestion: reverted ? null : {
            account_id: 'acct_posting', source: 'USER_RULE_APPLIED_DRAFT',
            safe_reason: '사용자가 승인한 규칙으로 검토 초안을 만들었습니다.',
            rule_id: 'rule_1234567890abcdef',
          },
        }],
      });
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      if (url.endsWith(`/v1/accounting/review/transactions/${TXN}/rule-application/revert`)) {
        reverted = true;
        return jsonResponse({
          schema_version: '3.0', txn_id: TXN, state: 'UNACCOUNTED',
          transaction_version: 2, rule_id: 'rule_1234567890abcdef',
          preserved_receipt_id: 'receipt_1234567890abcdef', event_hash: 'f'.repeat(64),
        });
      }
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '현재 건 초안 되돌리기' }));
    await screen.findByText('직접 확인 필요');
    const mutation = requests.find(request => request.url.endsWith('/rule-application/revert'));
    expect(mutation).toBeDefined();
    const headers = mutation?.init?.headers as Record<string, string>;
    expect(headers['If-Match']).toBe('W/"1"');
    expect(headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('shows a quarantined source row and recompiles through the product endpoint', async () => {
    let recompiled = false;
    const rowId = '00000000-0000-4000-8000-000000000111';
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/v1/accounting/review-capability')) return jsonResponse(capabilities);
      if (url.includes('/review-summary')) return jsonResponse({
        ...summary(),
        batch_version: recompiled ? 2 : 1,
        counts: { ...summary().counts, auto_propose: 0, review_required: recompiled ? 1 : 0, review_quarantine: recompiled ? 0 : 1 },
      });
      if (url.includes('/unaccounted')) return jsonResponse({
        ...page(), batch_version: recompiled ? 2 : 1, items: [], total_count: 0,
      });
      if (url.endsWith('/v1/accounting/review/batches/batch_1/quarantine')) return jsonResponse({
        schema_version: '3.0', batch_id: 'batch_1', items: [{
          row_id: rowId, batch_id: 'batch_1', source_row_number: 7,
          source_row_fingerprint: '9'.repeat(64), reason_code: 'INVALID_AMOUNT',
          state: 'QUARANTINED', resource_version: 1,
        }],
      });
      if (url.endsWith(`/v1/accounting/review/batches/batch_1/quarantine/${rowId}/recompile`)) {
        recompiled = true;
        return jsonResponse({
          schema_version: '3.0', row_id: rowId, state: 'UNACCOUNTED',
          resource_version: 2, event_hash: '8'.repeat(64),
        });
      }
      if (url.includes('/chart-of-accounts')) return jsonResponse(registry);
      throw new Error(`UNEXPECTED_REQUEST:${url}`);
    }));

    render(<AccountingReviewPage batchId="batch_1" onBack={() => {}} />);
    expect(await screen.findByText('원본 7행')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('금액(원, 정수)'), { target: { value: '-5500' } });
    fireEvent.change(screen.getByLabelText('거래일'), { target: { value: '2026-08-01' } });
    fireEvent.click(screen.getByRole('button', { name: '검토 목록으로 재컴파일' }));
    await waitFor(() => expect(screen.queryByText('원본 7행')).not.toBeInTheDocument());
  });
});
