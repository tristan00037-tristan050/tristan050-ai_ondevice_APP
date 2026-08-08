const { mockInvoke } = vi.hoisted(() => ({ mockInvoke: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ invoke: mockInvoke }));

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nativeAuthorizedAccountingRequest } from './nativeAuthorizedRequest';

describe('Box5 native authorized request boundary', () => {
  beforeEach(() => {
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      value: {},
      configurable: true,
    });
    mockInvoke.mockReset();
    mockInvoke.mockResolvedValue({
      status: 200,
      content_type: 'application/json',
      body: '{"ok":true}',
    });
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it('passes only a typed intent and never a URL, method, token, or assertion', async () => {
    const response = await nativeAuthorizedAccountingRequest(
      'ASSIGNMENT_CREATE',
      'ACCOUNTING_TRANSACTION',
      'txn_1234567890abcdef',
      '/v1/accounting/unaccounted/txn_1234567890abcdef/assign',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': 'request-12345678',
          'If-Match': 'W/"3"',
        },
        body: '{"account_id":"acct_posting"}',
      },
    );
    expect(await response.json()).toEqual({ ok: true });
    expect(mockInvoke).toHaveBeenCalledOnce();
    const [, wire] = mockInvoke.mock.calls[0];
    expect(wire).toEqual({
      request: {
        action: 'ASSIGNMENT_CREATE',
        route_selector: 'ASSIGNMENT_MUTATION',
        resource_id: 'txn_1234567890abcdef',
        parent_resource_id: null,
        body_json: '{"account_id":"acct_posting"}',
        idempotency_key: 'request-12345678',
        if_match_version: 3,
      },
    });
    const serialized = JSON.stringify(wire).toLowerCase();
    expect(serialized).not.toContain('authorization');
    expect(serialized).not.toContain('http://');
    expect(serialized).not.toContain('butler-user');
  });

  it.each([
    ['Authorization', 'Bearer forged'],
    ['aUtHoRiZaTiOn', 'Bearer forged'],
    ['Butler-User-Authorization', 'forged.assertion.value'],
  ])('rejects renderer-controlled sensitive header %s', async (name, value) => {
    await expect(nativeAuthorizedAccountingRequest(
      'ASSIGNMENT_CREATE',
      'ACCOUNTING_TRANSACTION',
      'txn_1234567890abcdef',
      '/v1/accounting/unaccounted/txn_1234567890abcdef/assign',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': 'request-12345678',
          'If-Match': 'W/"1"',
          [name]: value,
        },
        body: '{}',
      },
    )).rejects.toThrow('RENDERER_AUTHORIZATION_HEADER_FORBIDDEN');
    expect(mockInvoke).not.toHaveBeenCalled();
  });

  it('rejects path or action mismatch before native authority is invoked', async () => {
    await expect(nativeAuthorizedAccountingRequest(
      'RULE_DEACTIVATE',
      'LEARNED_RULE',
      'rule_1234567890abcdef',
      '/v1/accounting/learned-rules/another-rule/deactivate',
      { method: 'POST' },
    )).rejects.toThrow('BOX5_RESOURCE_BINDING_INVALID');
    expect(mockInvoke).not.toHaveBeenCalled();
  });

  it('has no browser fallback outside the signed desktop runtime', async () => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    await expect(nativeAuthorizedAccountingRequest(
      'RULE_DEACTIVATE',
      'LEARNED_RULE',
      'rule_1234567890abcdef',
      '/v1/accounting/learned-rules/rule_1234567890abcdef/deactivate',
      {
        method: 'POST',
        headers: {
          'Idempotency-Key': 'request-12345678',
          'If-Match': 'W/"1"',
        },
      },
    )).rejects.toThrow('BOX5_NATIVE_AUTHORITY_REQUIRED');
    expect(mockInvoke).not.toHaveBeenCalled();
  });
});
