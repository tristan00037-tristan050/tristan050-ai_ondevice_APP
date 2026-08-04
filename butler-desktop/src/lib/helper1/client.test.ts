import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../sidecarFetch', () => ({
  sidecarFetch: vi.fn(),
}));

import { sidecarFetch } from '../sidecarFetch';
import {
  askHelper1,
  fetchHelper1Status,
  Helper1ClientError,
} from './client';

const mockedFetch = vi.mocked(sidecarFetch);
const WORKSPACE_ID = '90321a6a-f937-4d93-b018-d09e8cab4e72';
const REQUEST_ID = '9699ce0c-2597-42ea-a6fa-29cfcb2bb75e';

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('Helper1 client contracts', () => {
  beforeEach(() => mockedFetch.mockReset());

  it('accepts only the immutable fail-closed status boundary', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({
      schema_version: 'butler.helper1.status.v2',
      state: 'ASSET_MISSING',
      workspaces: [],
      product_release_allowed: false,
      runtime_activation_allowed: false,
      production_claim_allowed: false,
      external_network_allowed: false,
    }));
    await expect(fetchHelper1Status()).resolves.toMatchObject({
      state: 'ASSET_MISSING',
      runtime_activation_allowed: false,
    });
  });

  it('rejects a sidecar response that tries to raise activation authority', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({
      schema_version: 'butler.helper1.status.v2',
      state: 'READY',
      workspaces: [{ workspace_id: WORKSPACE_ID, state: 'READY' }],
      product_release_allowed: false,
      runtime_activation_allowed: true,
      production_claim_allowed: false,
      external_network_allowed: false,
    }));
    await expect(fetchHelper1Status()).rejects.toMatchObject({
      reasonCode: 'HELPER1_STATUS_INVALID',
    });
  });

  it('accepts a typed refusal even when HTTP status is 503', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({
      schema_version: 'butler.helper1.answer.v2',
      kind: 'REFUSED_ASSET_MISSING',
      answer: null,
      request_id: REQUEST_ID,
      workspace_id: WORKSPACE_ID,
      generation_id: null,
      reason_code: 'HELPER1_RUNTIME_NOT_BOOTSTRAPPED',
      model_identity_sha256: null,
      index_manifest_sha256: null,
      citations: [],
      release_receipt_sha256: null,
      execution_receipt: null,
    }, 503));
    await expect(askHelper1(WORKSPACE_ID, '회사 규정')).resolves.toMatchObject({
      kind: 'REFUSED_ASSET_MISSING',
      answer: null,
    });
  });

  it('rejects malformed evidence and never trusts a cast-only response', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({
      schema_version: 'butler.helper1.answer.v2',
      kind: 'ANSWERED',
      answer: '답변',
      request_id: REQUEST_ID,
      workspace_id: WORKSPACE_ID,
      generation_id: 'g1',
      reason_code: null,
      model_identity_sha256: 'a'.repeat(64),
      index_manifest_sha256: 'b'.repeat(64),
      citations: [{
        claim_id: 'c1',
        workspace_id: WORKSPACE_ID,
        generation_id: '00000000-0000-4000-8000-000000000003',
        chunk_id: 'k1',
        source_id: 's1',
        evidence_start: 10,
        evidence_end: 2,
        evidence_sha256: 'c'.repeat(64),
      }],
      release_receipt_sha256: 'd'.repeat(64),
      execution_receipt: {},
    }));
    await expect(askHelper1(WORKSPACE_ID, '회사 규정')).rejects.toBeInstanceOf(
      Helper1ClientError,
    );
  });
});
