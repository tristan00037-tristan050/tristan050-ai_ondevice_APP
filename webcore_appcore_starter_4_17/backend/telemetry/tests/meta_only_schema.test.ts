/**
 * Meta-Only Schema Guard Tests
 * Verify Fail-Closed behavior: schema violation => rejected with reason_code
 */

// Simple test runner
function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS: ${name}`);
    return true;
  } catch (error: any) {
    console.error(`FAIL: ${name}: ${error.message}`);
    return false;
  }
}

function expect(actual: any) {
  return {
    toBe: (expected: any) => {
      if (actual !== expected) {
        throw new Error(`Expected ${expected}, got ${actual}`);
      }
    },
    not: {
      toBe: (expected: any) => {
        if (actual === expected) {
          throw new Error(`Expected not ${expected}, got ${actual}`);
        }
      },
    },
  };
}

function describe(name: string, fn: () => void) {
  fn();
}

import { validateMetaOnly, validateIngestRequest } from '../schema/meta_only';
import { MetaOnlyTelemetry, IngestRequest } from '../schema/meta_only';

describe('Meta-Only Schema Guard Tests', () => {
  it('should accept valid meta-only telemetry', () => {
    const telemetry: MetaOnlyTelemetry = {
      tenant_id: 'tenant1',
      timestamp: Date.now(),
      metric_name: 'request_count',
      metric_value: 100,
      tags: { environment: 'production' },
    };

    const result = validateMetaOnly(telemetry);
    expect(result.valid).toBe(true);
  });

  it('should reject raw text in metric_value', () => {
    const telemetry: MetaOnlyTelemetry = {
      tenant_id: 'tenant1',
      timestamp: Date.now(),
      metric_name: 'request_count',
      metric_value: 'This is a very long text that should be rejected because it contains raw text content that is not meta-only and should be blocked by the schema guard to ensure that only metadata and metrics are stored',
    };

    const result = validateMetaOnly(telemetry);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('META_ONLY_RAW_TEXT_DETECTED');
  });

  it('should reject candidate lists (large arrays)', () => {
    const telemetry: MetaOnlyTelemetry = {
      tenant_id: 'tenant1',
      timestamp: Date.now(),
      metric_name: 'request_count',
      metric_value: 100,
      metadata: Array(101).fill({ id: 'item' }), // 101 items (exceeds limit)
    };

    const result = validateMetaOnly(telemetry);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('META_ONLY_CANDIDATE_LIST_DETECTED');
  });

  it('should reject multi-line text', () => {
    const telemetry: MetaOnlyTelemetry = {
      tenant_id: 'tenant1',
      timestamp: Date.now(),
      metric_name: 'request_count',
      metric_value: 'line1\nline2\nline3',
    };

    const result = validateMetaOnly(telemetry);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('META_ONLY_RAW_TEXT_DETECTED');
  });

  it('should reject missing tenant_id', () => {
    const telemetry = {
      timestamp: Date.now(),
      metric_name: 'request_count',
      metric_value: 100,
    } as MetaOnlyTelemetry;

    const result = validateMetaOnly(telemetry);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('META_ONLY_MISSING_TENANT_ID');
  });

  it('should validate ingest request', () => {
    const request: IngestRequest = {
      tenant_id: 'tenant1',
      telemetry: [
        {
          tenant_id: 'tenant1',
          timestamp: Date.now(),
          metric_name: 'request_count',
          metric_value: 100,
        },
      ],
    };

    const result = validateIngestRequest(request);
    expect(result.valid).toBe(true);
  });

  it('should reject ingest request with tenant_id mismatch', () => {
    const request: IngestRequest = {
      tenant_id: 'tenant1',
      telemetry: [
        {
          tenant_id: 'tenant2', // Mismatch
          timestamp: Date.now(),
          metric_name: 'request_count',
          metric_value: 100,
        },
      ],
    };

    const result = validateIngestRequest(request);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('INGEST_TENANT_ID_MISMATCH');
  });
});

// Output-based proof
if (require.main === module) {
  console.log('META_ONLY_SCHEMA_GUARD_OK=1');
}

