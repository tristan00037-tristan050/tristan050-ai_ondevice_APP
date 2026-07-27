import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./sidecarFetch', () => ({ sidecarFetch: vi.fn() }));

import { sidecarFetch } from './sidecarFetch';
import { canonicalEgressReceiptPayload, useEgressReport } from './egressReport';

const mockedFetch = vi.mocked(sidecarFetch);
const KEY_ID = 'butler-egress-verifier-hook-test-v1';
const { privateKey, publicKey } = generateKeyPairSync('ed25519');

beforeAll(() => {
  vi.stubEnv('VITE_EGRESS_RECEIPT_KEY_ID', KEY_ID);
  vi.stubEnv(
    'VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64',
    publicKey.export({ format: 'der', type: 'spki' }).toString('base64'),
  );
});

afterAll(() => vi.unstubAllEnvs());

function report(
  runId: string,
  bytes = 0,
  measurementGeneration = runId === 'run-B' ? 2 : 1,
) {
  const measured = new Date();
  const payload = {
    schema_version: 'butler.egress.report.v3',
    measurement: 'MEASURED' as const,
    value: bytes,
    run_id: runId,
    measurement_generation: measurementGeneration,
    measurement_started_at: new Date(measured.getTime() - 1_000).toISOString(),
    measured_at: measured.toISOString(),
    fresh_until: new Date(measured.getTime() + 60_000).toISOString(),
    egress_bytes_total: bytes,
    external_request_count: bytes > 0 ? 1 : 0,
    raw_file_sent_external: false,
    verdict: (bytes > 0 ? 'FAIL' : 'PASS') as 'FAIL' | 'PASS',
    receipt_run_id: runId,
    receipt_key_id: KEY_ID,
    receipt_algorithm: 'Ed25519' as const,
    receipt_policy_version: 'egress-policy-2026.1',
    receipt_digest: `sha256:${'0'.repeat(64)}` as `sha256:${string}`,
    receipt_signature: 'A'.repeat(86),
  };
  const digest = createHash('sha256')
    .update(canonicalEgressReceiptPayload(payload))
    .digest('hex');
  payload.receipt_digest = `sha256:${digest}`;
  payload.receipt_signature = sign(
    null,
    Buffer.from(payload.receipt_digest, 'utf8'),
    privateKey,
  ).toString('base64url');
  return payload;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('useEgressReport transport and generation contract', () => {
  beforeEach(() => mockedFetch.mockReset());

  it.each([
    [new Response('{}', { status: 500, headers: { 'content-type': 'application/json' } }), 'HTTP_ERROR'],
    [new Response('{}', { status: 200, headers: { 'content-type': 'text/plain' } }), 'INVALID_CONTENT_TYPE'],
    [new Response('{', { status: 200, headers: { 'content-type': 'application/json' } }), 'INVALID_JSON'],
  ] as const)('sanitizes transport failure %#', async (response, code) => {
    mockedFetch.mockResolvedValueOnce(response);
    const { result } = renderHook(() => useEgressReport());
    await waitFor(() => expect(result.current.state.kind).toBe('error'));
    expect(result.current.state).toMatchObject({ kind: 'error', code });
    expect(JSON.stringify(result.current.state)).not.toContain('Response');
  });

  it.each([
    new Response(JSON.stringify({ detail: 'EGRESS_MEASUREMENT_UNAVAILABLE' }), {
      status: 503,
      headers: { 'content-type': 'application/json' },
    }),
    jsonResponse({
      value: 0,
      measurement: 'STATIC_BETA',
      measured_at: null,
    }),
  ])('maps unavailable and beta constants to an explicit unmeasured state', async response => {
    mockedFetch.mockResolvedValueOnce(response);
    const { result } = renderHook(() => useEgressReport());
    await waitFor(() => expect(result.current.state.kind).toBe('unmeasured'));
    expect(result.current.state).toMatchObject({ kind: 'unmeasured' });
    expect(JSON.stringify(result.current.state)).not.toContain('ready');
  });

  it('keeps loading visible while the measurement is unresolved', async () => {
    mockedFetch.mockImplementationOnce(() => new Promise(() => undefined));
    const { result, unmount } = renderHook(() => useEgressReport());
    expect(result.current.state).toEqual({ kind: 'loading', generation: 1 });
    unmount();
  });

  it('latest generation wins when an older request resolves last', async () => {
    let resolveA: ((response: Response) => void) | undefined;
    mockedFetch
      .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveA = resolve; }))
      .mockResolvedValueOnce(jsonResponse(report('run-B', 2048)));

    const { result } = renderHook(() => useEgressReport());
    await act(async () => {
      await result.current.refresh();
    });
    await waitFor(() => expect(result.current.state.kind).toBe('ready'));
    expect(result.current.state.kind === 'ready' && result.current.state.report.runId).toBe('run-B');

    await act(async () => {
      resolveA?.(jsonResponse(report('run-A', 0)));
      await Promise.resolve();
    });
    expect(result.current.state.kind === 'ready' && result.current.state.report.runId).toBe('run-B');
    expect(result.current.state.generation).toBe(2);
  });

  it.each([2, 3])(
    'rejects lower and duplicate signed measurement generation %s for one run',
    async replayedGeneration => {
      mockedFetch
        .mockResolvedValueOnce(jsonResponse(report('run-replay', 2048, 3)))
        .mockResolvedValueOnce(jsonResponse(report('run-replay', 0, replayedGeneration)));

      const { result } = renderHook(() => useEgressReport());
      await waitFor(() => expect(result.current.state.kind).toBe('ready'));
      expect(
        result.current.state.kind === 'ready'
          && result.current.state.report.measurementGeneration,
      ).toBe(3);

      await act(async () => {
        await result.current.refresh();
      });
      expect(result.current.state).toMatchObject({
        kind: 'error',
        code: 'MEASUREMENT_REPLAY',
      });
      expect(JSON.stringify(result.current.state)).not.toContain('밖으로 나간 것 0');
    },
  );
});
