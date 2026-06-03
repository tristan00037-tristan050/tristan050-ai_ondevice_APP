import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AdminPolicyConsole } from '../components/v1_1/AdminPolicyConsole';
import { ADMIN_POLICY_ENDPOINTS, ADMIN_POLICY_SIDECAR_ORIGIN, assertLocalAdminPolicyUrl } from '../lib/admin_policy/contracts';

const DIGEST = 'sha256:' + 'a'.repeat(64);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('AdminPolicyConsole v1.2', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts to the measured #772 company-policy endpoint with X-Admin headers only', async () => {
    const fetcher = vi.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse({
        schema_version: 'admin.company_policy_register.response.v1',
        policy_digest: DIGEST,
        audit_ref: DIGEST,
        admin_rbac_verified: true,
        raw_saved_zero: true,
        raw_text_logged: false,
      }),
    );

    render(<AdminPolicyConsole onClose={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.click(screen.getByRole('button', { name: '정책 등록' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${ADMIN_POLICY_SIDECAR_ORIGIN}${ADMIN_POLICY_ENDPOINTS.registerPolicy}`);
    expect((init.headers as Record<string, string>)['X-Admin-Role']).toBe('admin');
    expect((init.headers as Record<string, string>)['X-Admin-Id-Digest']).toBe(DIGEST);
    expect((init.headers as Record<string, string>)['Authorization']).toBeUndefined();
    expect(String(init.body)).toContain('"masking_engine_verified":false');
    expect(String(init.body)).not.toContain('external_send_rules');
    expect(await screen.findByTestId('admin-policy-success')).toHaveTextContent(DIGEST);
  });

  it('keeps external_send_rules read-only because #772 POST payload does not support editing', () => {
    render(<AdminPolicyConsole onClose={() => undefined} />);

    expect(screen.getByLabelText('restricted external send')).toHaveValue('차단');
    expect(screen.getByLabelText('confidential external send')).toHaveValue('차단');
    expect(screen.getByLabelText('internal external send')).toHaveValue('검토 필요');
    expect(screen.getByLabelText('public external send')).toHaveValue('허용');
    expect(screen.getByText(/external_send_rules가 없습니다/)).toBeInTheDocument();
  });

  it('shows admin permission error on backend AdminAuthError without retrying', async () => {
    const fetcher = vi.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse({ detail: { fail_class: 'ADMIN_RBAC_DENIED', message: 'admin role required' } }, 403),
    );

    render(<AdminPolicyConsole onClose={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.click(screen.getByRole('button', { name: '정책 등록' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('관리자 권한이 필요합니다');
  });

  it('rejects non-local admin policy URLs in the contract guard', () => {
    expect(() => assertLocalAdminPolicyUrl('http://localhost:8765/v1/admin/company-policy')).toThrow('BLOCK_NON_LOCAL_ADMIN_POLICY_URL');
    expect(() => assertLocalAdminPolicyUrl('https://example.invalid/v1/admin/company-policy')).toThrow('BLOCK_NON_LOCAL_ADMIN_POLICY_URL');
  });
});
