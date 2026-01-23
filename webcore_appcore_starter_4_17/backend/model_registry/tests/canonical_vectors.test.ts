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
});

