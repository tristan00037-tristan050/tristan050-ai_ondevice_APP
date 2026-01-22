/**
 * Signature Verification Helper
 * Validates signed requests according to SVR03_SIGNING_CANONICAL_PAYLOAD_V1.md
 * Fail-closed: missing/invalid signature => deny with reason_code
 */

import * as crypto from 'crypto';
import { verify } from '../services/signing';

export type SignatureValidationResult =
  | { valid: true }
  | { valid: false; reason_code: string; status: number };

/**
 * Create canonical JSON payload (v1)
 * Keys sorted lexicographically, minimal whitespace
 */
function createCanonicalPayload(
  op: string,
  tenantId: string,
  body: Record<string, unknown>
): string {
  const payload = {
    v: 'v1',
    ts_ms: Date.now(),
    tenant_id: tenantId,
    op,
    body: Object.keys(body)
      .sort()
      .reduce((acc, key) => {
        acc[key] = body[key];
        return acc;
      }, {} as Record<string, unknown>),
  };
  return JSON.stringify(payload);
}

/**
 * Get signing key by key_id (mock for now)
 * TODO: Implement key lookup from key store
 */
function getSigningKey(keyId: string): { publicKey: string } | null {
  // Mock: return a test key for now
  // In production, this should look up from key store
  if (keyId === 'test-key-1') {
    return {
      publicKey: 'test-public-key-base64',
    };
  }
  return null;
}

/**
 * Verify signature for artifact register request
 */
export function verifyArtifactRegisterSignature(
  tenantId: string,
  body: {
    model_id: string;
    version_id: string;
    platform: string;
    runtime: string;
    sha256: string;
    size_bytes: number;
    storage_ref: string;
  },
  signature?: string,
  sig_alg?: string,
  key_id?: string
): SignatureValidationResult {
  // Fail-closed: signature required
  if (!signature) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  if (!sig_alg || !key_id) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  // Get signing key
  const key = getSigningKey(key_id);
  if (!key) {
    return {
      valid: false,
      reason_code: 'KEY_ID_UNKNOWN',
      status: 400,
    };
  }

  // Create canonical payload
  const canonicalPayload = createCanonicalPayload('ARTIFACT_REGISTER', tenantId, {
    model_id: body.model_id,
    version_id: body.version_id,
    platform: body.platform,
    runtime: body.runtime,
    sha256: body.sha256,
    size_bytes: body.size_bytes,
    storage_ref: body.storage_ref,
  });

  // Verify signature
  const isValid = verify(
    Buffer.from(canonicalPayload, 'utf-8'),
    signature,
    key.publicKey
  );

  if (!isValid) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_INVALID',
      status: 403,
    };
  }

  return { valid: true };
}

/**
 * Verify signature for delivery apply request
 */
export function verifyDeliveryApplySignature(
  tenantId: string,
  body: {
    model_id: string;
    version_id: string;
    artifact_id: string;
    target: {
      device_class: string;
      min_app_version: string;
    };
  },
  signature?: string,
  sig_alg?: string,
  key_id?: string
): SignatureValidationResult {
  // Fail-closed: signature required
  if (!signature) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  if (!sig_alg || !key_id) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  // Get signing key
  const key = getSigningKey(key_id);
  if (!key) {
    return {
      valid: false,
      reason_code: 'KEY_ID_UNKNOWN',
      status: 400,
    };
  }

  // Create canonical payload
  const canonicalPayload = createCanonicalPayload('DELIVERY_APPLY', tenantId, {
    model_id: body.model_id,
    version_id: body.version_id,
    artifact_id: body.artifact_id,
    target: body.target,
  });

  // Verify signature
  const isValid = verify(
    Buffer.from(canonicalPayload, 'utf-8'),
    signature,
    key.publicKey
  );

  if (!isValid) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_INVALID',
      status: 403,
    };
  }

  return { valid: true };
}

/**
 * Verify signature for delivery rollback request
 */
export function verifyDeliveryRollbackSignature(
  tenantId: string,
  body: {
    model_id: string;
    version_id: string;
    artifact_id: string;
    reason_code: string;
  },
  signature?: string,
  sig_alg?: string,
  key_id?: string
): SignatureValidationResult {
  // Fail-closed: signature required
  if (!signature) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  if (!sig_alg || !key_id) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_MISSING',
      status: 400,
    };
  }

  // Get signing key
  const key = getSigningKey(key_id);
  if (!key) {
    return {
      valid: false,
      reason_code: 'KEY_ID_UNKNOWN',
      status: 400,
    };
  }

  // Create canonical payload
  const canonicalPayload = createCanonicalPayload('DELIVERY_ROLLBACK', tenantId, {
    model_id: body.model_id,
    version_id: body.version_id,
    artifact_id: body.artifact_id,
    reason_code: body.reason_code,
  });

  // Verify signature
  const isValid = verify(
    Buffer.from(canonicalPayload, 'utf-8'),
    signature,
    key.publicKey
  );

  if (!isValid) {
    return {
      valid: false,
      reason_code: 'SIGNATURE_INVALID',
      status: 403,
    };
  }

  return { valid: true };
}

