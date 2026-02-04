/**
 * Telemetry HTTP E2E Tests (fail-closed)
 * 목적: 네트워크 경계(HTTP)에서 meta-only 위반이 저장 0으로 봉인되는지 검증
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - Jest-only (describe/it/expect)
 */

import express from 'express';
import { describe, it, expect, beforeEach, afterAll } from '@jest/globals';
import ingestRouter from '../api/ingest';
import { clearStorage, queryTelemetry } from '../store/service';

// ---- Test-only auth/rbac stubs (fail-closed semantics 테스트가 목적이므로 인증 자체는 통과시키되 tenant는 고정) ----
jest.mock('../../control_plane/auth/middleware', () => {
  return {
    requireAuth: async (req: any, _res: any, next: any) => {
      // 테스트용 인증 컨텍스트 주입
      req.authContext = { tenant_id: 'tenant1', user_id: 'u1', roles: [] };
      // rbac가 참조하는 userRoles도 주입(tenant:write 허용)
      req.userRoles = [{ permissions: ['tenant:write'] }];
      next();
    },
    extractTenantId: (req: any) => req.authContext?.tenant_id ?? null,
  };
});

jest.mock('../../control_plane/auth/rbac', () => {
  return {
    requirePermission: (_perm: any) => (_req: any, _res: any, next: any) => next(),
  };
});

// ---- HTTP 서버 유틸 ----
async function startServer() {
  const app = express();
  app.use(express.json());
  app.use('/api/v1/telemetry', ingestRouter);

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

describe('Telemetry HTTP E2E (fail-closed)', () => {
  let server: import('http').Server;
  let baseUrl: string;

  beforeEach(() => {
    clearStorage();
  });

  afterAll(() => {
    if (server) server.close();
  });

  it('rejects identifier-like token and stores 0', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/telemetry/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        telemetry: [
          {
            tenant_id: 'tenant1',
            timestamp: Date.now(),
            metric_name: 'request_count',
            metric_value: 1,
            tags: { session_id: '550e8400-e29b-41d4-a716-446655440000' }, // UUID
          },
        ],
      }),
    });

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(String(json.reason_code || '')).toContain('IDENTIFIER');

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(0);
  });

  it('rejects raw text and stores 0', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/telemetry/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        telemetry: [
          {
            tenant_id: 'tenant1',
            timestamp: Date.now(),
            metric_name: 'request_count',
            metric_value: 'a'.repeat(1001), // raw text
          },
        ],
      }),
    });

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(String(json.reason_code || '')).toContain('RAW_TEXT');

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(0);
  });

  it('rejects tenant mismatch and stores 0 (HTTP boundary)', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    // auth tenant is 'tenant1' (stub), but request tenant_id is 'tenant2'
    const res = await fetch(`${baseUrl}/api/v1/telemetry/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant2',
        telemetry: [
          {
            tenant_id: 'tenant2',
            timestamp: Date.now(),
            metric_name: 'request_count',
            metric_value: 1,
          },
        ],
      }),
    });

    expect(res.status).toBe(403);
    const json = await res.json();
    expect(String(json.reason_code || '')).toBe('INGEST_TENANT_MISMATCH');

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(0);
  });

  it('accepts valid meta-only payload and stores 1', async () => {
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;

    const res = await fetch(`${baseUrl}/api/v1/telemetry/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'tenant1',
        telemetry: [
          {
            tenant_id: 'tenant1',
            timestamp: Date.now(),
            metric_name: 'request_count',
            metric_value: 100,
            tags: { environment: 'production', region: 'kr' },
          },
        ],
      }),
    });

    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.ingested_count).toBe(1);
    expect(json.rejected_count).toBe(0);

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(1);
  });
});

