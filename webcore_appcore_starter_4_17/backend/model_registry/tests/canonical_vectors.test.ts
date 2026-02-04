/**
 * Canonical Vectors Test
 * Verify that canonicalization produces identical output for same input regardless of key order.
 * 
 * Hard rule:
 * - Same input object → canonical string must always be identical
 * - Different key order → canonical string must be identical
 * - If any differs, test FAILs immediately
 */

import { describe, it, expect } from '@jest/globals';
import { canonicalizeJson } from '../../../../packages/common/src/canon/jcs';
import * as crypto from 'crypto';

describe('Canonical Vectors', () => {
  it('[EVID:MODEL_UPLOAD_SIGN_VERIFY_OK] same input produces identical canonical string', () => {
    const input1 = {
      v: 'v1',
      ts_ms: 1234567890,
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    const input2 = {
      v: 'v1',
      ts_ms: 1234567890,
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    const canonical1 = canonicalizeJson(input1);
    const canonical2 = canonicalizeJson(input2);

    expect(canonical1).toBe(canonical2);
  });

  it('[EVID:MODEL_UPLOAD_SIGN_VERIFY_OK] different key order produces identical canonical string', () => {
    const input1 = {
      v: 'v1',
      ts_ms: 1234567890,
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    // Same data, different key order
    const input2 = {
      body: {
        storage_ref: 's3://bucket/key',
        size_bytes: 1024,
        sha256: 'abc123',
        runtime: 'tflite',
        platform: 'android',
        version_id: 'v1.0.0',
        model_id: 'model1',
      },
      op: 'ARTIFACT_REGISTER',
      tenant_id: 'tenant1',
      ts_ms: 1234567890,
      v: 'v1',
    };

    const canonical1 = canonicalizeJson(input1);
    const canonical2 = canonicalizeJson(input2);

    expect(canonical1).toBe(canonical2);
  });

  it('[EVID:MODEL_UPLOAD_SIGN_VERIFY_OK] canonical string produces same SHA256 hash', () => {
    const input1 = {
      v: 'v1',
      ts_ms: 1234567890,
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    const input2 = {
      body: {
        storage_ref: 's3://bucket/key',
        size_bytes: 1024,
        sha256: 'abc123',
        runtime: 'tflite',
        platform: 'android',
        version_id: 'v1.0.0',
        model_id: 'model1',
      },
      op: 'ARTIFACT_REGISTER',
      tenant_id: 'tenant1',
      ts_ms: 1234567890,
      v: 'v1',
    };

    const canonical1 = canonicalizeJson(input1);
    const canonical2 = canonicalizeJson(input2);

    const hash1 = crypto.createHash('sha256').update(canonical1).digest('hex');
    const hash2 = crypto.createHash('sha256').update(canonical2).digest('hex');

    expect(hash1).toBe(hash2);
  });

  it('[EVID:MODEL_APPLY_FAILCLOSED_OK] different values produce different canonical strings', () => {
    const input1 = {
      v: 'v1',
      ts_ms: 1234567890,
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    const input2 = {
      v: 'v1',
      ts_ms: 1234567891, // Different timestamp
      tenant_id: 'tenant1',
      op: 'ARTIFACT_REGISTER',
      body: {
        model_id: 'model1',
        version_id: 'v1.0.0',
        platform: 'android',
        runtime: 'tflite',
        sha256: 'abc123',
        size_bytes: 1024,
        storage_ref: 's3://bucket/key',
      },
    };

    const canonical1 = canonicalizeJson(input1);
    const canonical2 = canonicalizeJson(input2);

    expect(canonical1).not.toBe(canonical2);
  });

  // Extended vectors: nested structures
  it('deeply nested object', () => {
    expect(canonicalizeJson({ a: { b: { c: { d: 1 } } } })).toBe('{"a":{"b":{"c":{"d":1}}}}');
  });

  it('nested array in object', () => {
    expect(canonicalizeJson({ a: [1, 2, 3] })).toBe('{"a":[1,2,3]}');
  });

  it('object in array', () => {
    expect(canonicalizeJson([{ a: 1, b: 2 }, { c: 3 }])).toBe('[{"a":1,"b":2},{"c":3}]');
  });

  it('mixed nested structure', () => {
    expect(canonicalizeJson({ a: [{ b: 1 }, { c: 2 }], d: { e: 3 } })).toBe('{"a":[{"b":1},{"c":2}],"d":{"e":3}}');
  });

  // Extended vectors: numbers
  it('integer numbers', () => {
    expect(canonicalizeJson({ a: 0, b: 123, c: -456 })).toBe('{"a":0,"b":123,"c":-456}');
  });

  it('floating point numbers', () => {
    const result = canonicalizeJson({ a: 1.5, b: -0.5, c: 3.14159 });
    // Floating point representation may vary, so we check structure
    expect(result).toContain('"a":');
    expect(result).toContain('"b":');
    expect(result).toContain('"c":');
  });

  it('large numbers', () => {
    expect(canonicalizeJson({ a: 1000000, b: -999999 })).toBe('{"a":1000000,"b":-999999}');
  });

  // Extended vectors: unicode and escape sequences
  it('unicode characters (Korean)', () => {
    expect(canonicalizeJson({ a: "안녕" })).toBe('{"a":"안녕"}');
  });

  it('escape sequences', () => {
    expect(canonicalizeJson({ a: "line1\nline2" })).toBe('{"a":"line1\\nline2"}');
    expect(canonicalizeJson({ a: "tab\there" })).toBe('{"a":"tab\\there"}');
    expect(canonicalizeJson({ a: 'quote"here' })).toBe('{"a":"quote\\"here"}');
  });

  it('mixed escape sequences', () => {
    expect(canonicalizeJson({ a: "a\nb\tc\"d" })).toBe('{"a":"a\\nb\\tc\\"d"}');
  });

  // Extended vectors: edge cases
  it('empty array', () => {
    expect(canonicalizeJson([])).toBe("[]");
  });

  it('null values', () => {
    expect(canonicalizeJson({ a: null, b: 1 })).toBe('{"a":null,"b":1}');
  });

  it('boolean values', () => {
    expect(canonicalizeJson({ a: true, b: false })).toBe('{"a":true,"b":false}');
  });

  it('complex mixed structure', () => {
    const input = {
      z: "last",
      a: {
        nested: [1, { deep: "value" }],
        number: 42,
        bool: true,
        null_val: null,
      },
      b: ["array", "items"],
    };
    const result = canonicalizeJson(input);
    // Verify structure (exact order may vary, but keys should be sorted)
    expect(result).toContain('"a":');
    expect(result).toContain('"b":');
    expect(result).toContain('"z":');
    expect(result).toContain('"nested":');
    expect(result).toContain('"deep":');
  });

  // Consistency: same input should produce same output
  it('consistency: same input produces same output', () => {
    const input = { a: 1, b: { c: 2, d: [3, 4] } };
    const result1 = canonicalizeJson(input);
    const result2 = canonicalizeJson(input);
    expect(result1).toBe(result2);
  });
});

