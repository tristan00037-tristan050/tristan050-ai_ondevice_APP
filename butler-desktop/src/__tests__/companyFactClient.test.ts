import { describe, expect, it, vi } from 'vitest';
import {
  CompanyFactClientError,
  approveCompanyFactCandidate,
  deprecateCompanyFact,
  getCompanyFactsStatus,
  listCompanyFactCandidates,
  overrideKnownBadCandidate,
  supersedeCompanyFact,
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
const CAP_TOKEN = 'cap-token-xyz';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const tokenProvider = async () => CAP_TOKEN;

describe('company_fact client', () => {
  it('sends Bearer token + x-admin headers to the list endpoint', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ candidates: [], raw_text_logged: false, external_send_zero: true }));
    await listCompanyFactCandidates(ADMIN, { fetcher, tokenProvider });

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.listCandidates}`);
    expect(init.method).toBe('GET');
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe(`Bearer ${CAP_TOKEN}`);
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
    expect(headers['Authorization']).toBe(`Bearer ${CAP_TOKEN}`);
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

  it('posts deprecate reason as a single JSON object', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({ fact_id: 'F1', status: 'DEPRECATED', raw_text_logged: false, external_send_zero: true }),
    );
    await deprecateCompanyFact('F1', 'WRONG', ADMIN, { fetcher, tokenProvider });

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.deprecateFact('F1')}`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ reason_code: 'WRONG' });
  });

  it('posts supersede to the active fact endpoint with confidence fixed at 1.0', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'company_fact.supersede.result.v1',
        old_fact_id: 'F1',
        old_status: 'DEPRECATED',
        old_fact_digest: `sha256:${'b'.repeat(64)}`,
        new_fact_id: 'F2',
        new_status: 'ACTIVE',
        new_fact_digest: `sha256:${'c'.repeat(64)}`,
        previous_fact_digest: `sha256:${'b'.repeat(64)}`,
        audit_refs: [`sha256:${'d'.repeat(64)}`],
        raw_text_logged: false,
        external_send_zero: true,
      }),
    );
    await supersedeCompanyFact(
      'F1',
      {
        category: 'policy',
        question_patterns: ['q1', 'q2'],
        keywords_required: ['required'],
        keywords_any: ['any'],
        answer_runtime_text: 'updated official answer',
        source: 'admin',
        source_url: null,
        source_doc: null,
        verified_at: null,
        expires_at: null,
        confidence: 1.0,
      },
      ADMIN,
      { fetcher, tokenProvider },
    );

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.supersedeFact('F1')}`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ confidence: 1.0, question_patterns: ['q1', 'q2'] });
  });

  it('posts known-bad override to the candidate-scoped endpoint with admin headers', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'company_fact.known_bad_override.response.v1',
        fact_id: 'F1',
        candidate_fact_digest: `sha256:${'b'.repeat(64)}`,
        bad_entry_id: 'bad-1',
        bad_fact_digest: `sha256:${'c'.repeat(64)}`,
        approved_by_digest: DIGEST,
        approved_at: '2026-06-20T00:00:00Z',
        status: 'ACTIVE',
        override_digest: `sha256:${'d'.repeat(64)}`,
        audit_ref: `sha256:${'e'.repeat(64)}`,
        raw_text_logged: false,
        external_send_zero: true,
      }),
    );
    await overrideKnownBadCandidate('F1', ADMIN, { fetcher, tokenProvider });

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_FACT_ENDPOINTS.overrideKnownBad('F1')}`);
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers['x-admin-role']).toBe('admin');
    expect(init.body).toBeUndefined();
  });

  it('surfaces backend fail_class on non-2xx responses', async () => {
    const fetcher = vi.fn(async () =>
      jsonResponse({ detail: { fail_class: 'ADMIN_ROLE_NOT_REGISTERED', message: 'not a registered admin' } }, 403),
    );
    let error: unknown;
    try {
      await listCompanyFactCandidates(ADMIN, { fetcher, tokenProvider });
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(CompanyFactClientError);
    if (!(error instanceof CompanyFactClientError)) {
      throw new Error('EXPECTED_COMPANY_FACT_CLIENT_ERROR');
    }
    expect(error.failClass).toBe('ADMIN_ROLE_NOT_REGISTERED');
    expect(error.status).toBe(403);
  });
});
