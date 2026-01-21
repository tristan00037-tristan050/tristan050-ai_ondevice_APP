/**
 * Meta-Only Guard Tests
 * APP-04: SDK-side telemetry validation (fail-closed)
 * 
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - Jest-only (describe/it/expect), no custom runner
 */

import { describe, it, expect } from '@jest/globals';
import { validateTelemetryPayload } from './metaOnlyGuard';

describe('Meta-Only Guard (SDK-side)', () => {
  it('should reject payload with identifier-like token (UUID)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      userId: '550e8400-e29b-41d4-a716-446655440000', // UUID
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_IDENTIFIER_DETECTED');
    expect(result.message).toContain('userId');
  });

  it('should reject payload with identifier-like token (long hex)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      token: 'a1b2c3d4e5f6789012345678901234567890abcd', // 40-char hex
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_IDENTIFIER_DETECTED');
  });

  it('should reject payload with identifier-like token (JWT-like)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      jwt: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c',
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_IDENTIFIER_DETECTED');
  });

  it('should reject payload with raw text (long string)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      rawText: 'a'.repeat(1001), // > 1000 chars
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_RAW_TEXT_DETECTED');
  });

  it('should reject payload with raw text (newlines)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      message: 'line1\nline2\nline3',
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_RAW_TEXT_DETECTED');
  });

  it('should reject payload with candidate list (large array)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      candidates: Array(101).fill('item'), // > 100 items
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(false);
    expect(result.reason_code).toBe('SDK_META_ONLY_CANDIDATE_LIST_DETECTED');
  });

  it('should allow valid meta-only payload (numbers and enums only)', () => {
    const payload = {
      eventType: 'suggestion_shown',
      suggestionLength: 100,
      modelLoadMs: 500,
      inferenceMs: 1200,
      backend: 'stub',
      success: true,
      ragEnabled: true,
      ragDocs: 5,
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(true);
  });

  it('should allow valid meta-only payload (short enum strings)', () => {
    const payload = {
      eventType: 'suggestion_used_as_is',
      suggestionLength: 50,
      backend: 'real',
    };

    const result = validateTelemetryPayload(payload);
    expect(result.valid).toBe(true);
  });
});

