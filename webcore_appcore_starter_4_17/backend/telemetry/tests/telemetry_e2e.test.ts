/**
 * Telemetry E2E Tests
 * Verify meta-only schema guard and ingest behavior
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - no require.main side effects in tests
 * - Jest-only (describe/it/expect), no custom runner
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { validateIngestRequest, MetaOnlyTelemetry, IngestRequest } from '../schema/meta_only';
import { ingestTelemetry } from '../ingest/service';
import { queryTelemetry, clearStorage } from '../store/service';

describe('Telemetry E2E Verification', () => {
  beforeEach(() => {
    clearStorage();
  });
  it('should reject raw text payload and not store (fail-closed)', () => {
    const request: IngestRequest = {
      tenant_id: 'tenant1',
      telemetry: [
        {
          tenant_id: 'tenant1',
          timestamp: Date.now(),
          metric_name: 'request_count',
          metric_value: 'A'.repeat(1001),
        },
      ],
    };

    const validation = validateIngestRequest(request);
    expect(validation.valid).toBe(false);
    if (!validation.valid) {
      expect(validation.reason_code).toContain('RAW_TEXT');
    }

    const result = ingestTelemetry(request);
    expect(result.success).toBe(false);
    expect(result.ingested_count).toBe(0);
    expect(result.rejected_count).toBe(1);
    expect(result.reason_code).toBeTruthy();

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(0);
  });

  it('should reject identifier-like token payload and not store (fail-closed)', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';

    const request: IngestRequest = {
      tenant_id: 'tenant1',
      telemetry: [
        {
          tenant_id: 'tenant1',
          timestamp: Date.now(),
          metric_name: 'request_count',
          metric_value: 1,
          tags: { session_id: uuid },
        },
      ],
    };

    const validation = validateIngestRequest(request);
    expect(validation.valid).toBe(false);
    if (!validation.valid) {
      expect(validation.reason_code).toContain('IDENTIFIER');
    }

    const result = ingestTelemetry(request);
    expect(result.success).toBe(false);
    expect(result.ingested_count).toBe(0);
    expect(result.rejected_count).toBe(1);
    expect(result.reason_code).toBeTruthy();

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBe(0);
  });

  it('should allow meta-only payload and ingest successfully', () => {
    const request: IngestRequest = {
      tenant_id: 'tenant1',
      telemetry: [
        {
          tenant_id: 'tenant1',
          timestamp: Date.now(),
          metric_name: 'request_count',
          metric_value: 100,
          tags: { environment: 'production', region: 'us-east-1' },
        },
      ],
    };

    const validation = validateIngestRequest(request);
    expect(validation.valid).toBe(true);

    const result = ingestTelemetry(request);
    expect(result.success).toBe(true);
    expect(result.ingested_count).toBe(1);
    expect(result.rejected_count).toBe(0);

    const stored = queryTelemetry('tenant1');
    expect(stored.length).toBeGreaterThan(0);
    expect(stored[0].metric_name).toBe('request_count');
    expect(stored[0].metric_value).toBe(100);
  });
});

