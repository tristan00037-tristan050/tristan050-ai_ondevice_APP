import { describe, expect, it, vi } from 'vitest';
import {
  CompanyLearningClientError,
  connectCompanyLearningFolder,
  getCompanyLearningStatus,
  handoffCompanyLearningCandidate,
} from '../lib/company_learning/client';
import { COMPANY_LEARNING_ENDPOINTS } from '../lib/company_learning/contracts';
import type { AdminContextForSidecar } from '../lib/company_learning/contracts';
import { SIDECAR_BASE } from '../constants';

const DIGEST = `sha256:${'a'.repeat(64)}` as `sha256:${string}`;
const ZERO = `sha256:${'0'.repeat(64)}` as `sha256:${string}`;
const CAP_TOKEN = 'company-learning-cap-token';

const ADMIN: AdminContextForSidecar = {
  role: 'admin',
  admin_id_digest: DIGEST,
  admin_session_digest: DIGEST,
  auth_method: 'os_keychain',
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const tokenProvider = async () => CAP_TOKEN;

describe('company_learning client', () => {
  it('posts selected folder path as a single JSON object and attaches admin headers', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'company_learning.connect.response.v1',
        job_id: 'clj-1',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        counters: {
          scanned_files: 1,
          processed_files: 1,
          skipped_unsupported: 0,
          skipped_hidden: 0,
          skipped_symlink: 0,
          skipped_limit: 0,
          skipped_extractor: 0,
          failed_extract: 0,
          total_bytes: 10,
          chunk_count: 1,
          by_extension: { '.txt': 1 },
        },
        raw_text_logged: false,
        external_send_zero: true,
      }),
    );

    await connectCompanyLearningFolder('/Users/me/private-folder', ADMIN, { fetcher, tokenProvider });

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_LEARNING_ENDPOINTS.connectFolder}`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ folder_path: '/Users/me/private-folder' });
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${CAP_TOKEN}`);
    expect(headers['x-admin-role']).toBe('admin');
    expect(headers['x-admin-id-digest']).toBe(DIGEST);
  });

  it('gets status with encoded job_id and no request body', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'company_learning.status.v1',
        job_id: 'clj/with space',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        progress: 100,
        counters: {
          scanned_files: 1,
          processed_files: 1,
          skipped_unsupported: 0,
          skipped_hidden: 0,
          skipped_symlink: 0,
          skipped_limit: 0,
          skipped_extractor: 0,
          failed_extract: 0,
          total_bytes: 10,
          chunk_count: 1,
          by_extension: {},
        },
        started_at: '2026-06-20T00:00:00Z',
        updated_at: '2026-06-20T00:00:00Z',
        error_code: null,
        raw_text_logged: false,
        external_send_zero: true,
      }),
    );

    await getCompanyLearningStatus('clj/with space', ADMIN, { fetcher, tokenProvider });

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}/v1/company-learning/status?job_id=clj%2Fwith%20space`);
    expect(init.method).toBe('GET');
    expect(init.body).toBeUndefined();
  });

  it('posts handoff confirmation as a body object', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'company_learning.handoff.response.v1',
        job_id: 'clj-1',
        learning_event_id: 'lev-1',
        status: 'CANDIDATE',
        learning_type: 'memory_search',
        approved_text_ref: 'vault://company-learning/abc',
        approved_text_digest: DIGEST,
        sanitized_summary_digest: DIGEST,
        verified_for_training: false,
        policy_decision: 'needs_review',
        raw_text_logged: false,
        external_send_zero: true,
      }),
    );

    await handoffCompanyLearningCandidate('clj-1', true, ADMIN, { fetcher, tokenProvider });

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SIDECAR_BASE}${COMPANY_LEARNING_ENDPOINTS.handoff}`);
    expect(JSON.parse(String(init.body))).toEqual({ job_id: 'clj-1', admin_confirmed_needs_review: true });
  });

  it('blocks zero digest before any fetch', async () => {
    const fetcher = vi.fn();
    await expect(
      connectCompanyLearningFolder('/Users/me/private-folder', { ...ADMIN, admin_id_digest: ZERO }, { fetcher, tokenProvider }),
    ).rejects.toMatchObject({ failClass: 'ADMIN_DIGEST_PLACEHOLDER' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('surfaces backend fail_class without rendering raw backend message', async () => {
    const fetcher = vi.fn(async () =>
      jsonResponse({ detail: { fail_class: 'NO_INDEXABLE_FILES', message: 'NO_INDEXABLE_FILES' } }, 422),
    );
    let error: unknown;
    try {
      await connectCompanyLearningFolder('/Users/me/private-folder', ADMIN, { fetcher, tokenProvider });
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(CompanyLearningClientError);
    expect((error as CompanyLearningClientError).failClass).toBe('NO_INDEXABLE_FILES');
  });
});
