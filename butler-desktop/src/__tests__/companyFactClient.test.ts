import { describe, expect, it, vi } from 'vitest';
import {
  CompanyFactClientError,
  approveCompanyFactCandidate,
  getCompanyFactsStatus,
  listCompanyFactCandidates,
} from '../lib/company_fact/client';
import { COMPANY_FACT_ENDPOINTS } from '../lib/company_fact/contracts';
import type { AdminContextForSidecar } from '../lib/company_fact/contracts';
import { SIDECAR_BASE } from '../constants';

const DIGEST = `sha256:${'a'.repeat(64)}` as `sha256:${string}`;
const ZERO = `sha256:${'0'.repeat(64)}` as `sha256:${string}`;

const ADMIN: AdminContextForSidecar = {
  role: 'admin',
  admin_id_digest: DIGEST,
  admin_session_digest: DIGEST,
  auth_method: 'os_keychain',
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const tokenProvider = async () => 'cap-token-xyz';

describe('company_fact client', () => {
  it('sends Bearer token + x-admin headers to the list endpoint', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ candidates: [], raw_text_logged: false, external_send_zero: true }));
    await listCompanyFactCandidates(ADMIN, { fetcher, tokenProvider });

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.listCandidates}`);
    expect(init.method).toBe('GET');
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer cap-token-xyz');
    expect(headers['x-admin-role']).toBe('admin');
    expect(headers['x-admin-id-digest']).toBe(DIGEST);
    expect(headers['x-admin-session-digest']).toBe(DIGEST);
    expect(headers['x-admin-auth-method']).toBe('os_keychain');
  });

  it('blocks the zero-digest placeholder before any fetch', async () => {
    const fetcher = vi.fn();
    await expect(
      listCompanyFactCandidates({ ...ADMIN, admin_id_digest: ZERO }, { fetcher, tokenProvider }),
    ).rejects.toMatchObject({ failClass: 'ADMIN_DIGEST_PLACEHOLDER' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('blocks test_only auth method in production build before any fetch', async () => {
    const fetcher = vi.fn();
    await expect(
      listCompanyFactCandidates(
        { ...ADMIN, auth_method: 'test_only' },
        { fetcher, tokenProvider, isProduction: true },
      ),
    ).rejects.toMatchObject({ failClass: 'ADMIN_AUTH_METHOD_NOT_ALLOWED' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('status endpoint carries token only (no admin headers)', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({ active_count: 3, candidate_count: 2, raw_text_logged: false, external_send_zero: true }),
    );
    const status = await getCompanyFactsStatus({ fetcher, tokenProvider });
    expect(status.active_count).toBe(3);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.status}`);
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer cap-token-xyz');
    expect(headers['x-admin-role']).toBeUndefined();
  });

  it('posts approve to the candidate-scoped endpoint', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({ fact_id: 'F1', status: 'ACTIVE', raw_text_logged: false, external_send_zero: true }),
    );
    const res = await approveCompanyFactCandidate('F1', ADMIN, { fetcher, tokenProvider });
    expect(res.status).toBe('ACTIVE');
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.approveCandidate('F1')}`);
    expect(init.method).toBe('POST');
  });

  it('surfaces backend fail_class on non-2xx responses', async () => {
    const fetcher = vi.fn(async () =>
      jsonResponse({ detail: { fail_class: 'ADMIN_ROLE_NOT_REGISTERED', message: 'not a registered admin' } }, 403),
    );
    const error = await listCompanyFactCandidates(ADMIN, { fetcher, tokenProvider }).catch(
      (e: unknown) => e as CompanyFactClientError,
    );
    expect(error).toBeInstanceOf(CompanyFactClientError);
    expect(error.failClass).toBe('ADMIN_ROLE_NOT_REGISTERED');
    expect(error.status).toBe(403);
  });
});
