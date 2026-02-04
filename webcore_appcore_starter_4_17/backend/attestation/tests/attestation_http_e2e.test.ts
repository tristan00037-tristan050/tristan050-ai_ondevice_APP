/**
 * Attestation HTTP E2E Tests (fail-closed)
 * 목적: HTTP 경계에서 attestation proof 검증이 allow/deny로 봉인되는지 검증
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - Jest-only (describe/it/expect)
 */

import express from 'express';
import { describe, it, expect, beforeEach } from '@jest/globals';
import verifyRouter from '../api/verify';
import { clearStore, attestationStore } from '../store/memory';

// ---- Test-only auth stubs ----
jest.mock('../../control_plane/auth/middleware', () => {
  return {
    requireAuth: async (req: any, _res: any, next: any) => {
      req.authContext = { tenant_id: 'tenant1', user_id: 'u1', roles: [] };
      next();
    },
    extractTenantId: (req: any) => req.authContext?.tenant_id ?? null,
  };
});

// ---- HTTP 서버 유틸 ----
async function startServer() {
  const app = express();
  app.use(express.json());
  app.use('/api/v1/attestation', verifyRouter);

  const server = await new Promise<import('http').Server>((resolve) => {
    const s = app.listen(0, () => resolve(s));
  });

  const addr = server.address();
  if (!addr || typeof addr === 'string') {
    server.close();
    throw new Error('Failed to bind test server');
  }
  const baseUrl = `http://127.0.0.1:${addr.port}`;
  return { server, baseUrl };
}

describe('Attestation HTTP E2E (fail-closed)', () => {
  let server: import('http').Server;
  let baseUrl: string;

  beforeEach(() => {
    clearStore();
  });

  it('denies request with missing proof and stores 0 allows', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/attestation/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        proof: null,
      }),
    });

    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.allowed).toBe(false);
    expect(String(json.reason_code || '')).toContain('ATTEST_MISSING_PROOF');

    const allowCount = attestationStore.getAllowCount('tenant1');
    expect(allowCount).toBe(0);

    server.close();
  });

  it('denies request with invalid proof and stores 0 allows', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/attestation/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        proof: 'invalid-proof',
      }),
    });

    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.allowed).toBe(false);
    expect(String(json.reason_code || '')).toContain('ATTEST_INVALID_PROOF');

    const allowCount = attestationStore.getAllowCount('tenant1');
    expect(allowCount).toBe(0);

    server.close();
  });

  it('allows request with valid proof and stores 1 allow', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/attestation/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        proof: 'valid-proof',
      }),
    });

    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.allowed).toBe(true);

    const allowCount = attestationStore.getAllowCount('tenant1');
    expect(allowCount).toBe(1);

    server.close();
  });
});

