/**
 * Delivery Service
 * Apply and rollback operations with signature verification (fail-closed)
 */

import { verifyDeliveryApplySignature, verifyDeliveryRollbackSignature } from '../verify/signature';
import { appendAudit } from './audit';

export type ApplyResult =
  | { ok: true; applied: boolean }
  | { ok: false; reason_code: string; applied: false };

export type RollbackResult =
  | { ok: true; rolled_back: boolean }
  | { ok: false; reason_code: string; rolled_back: false };

/**
 * Apply artifact delivery (fail-closed on missing/invalid/expired signature)
 */
export function applyArtifact(
  tenantId: string,
  delivery: {
    sha256: string;
    signature?: string;
    key_id?: string;
    ts_ms?: number;
    expires_at?: number;
    model_id: string;
    version_id: string;
    artifact_id: string;
    target?: {
      device_class: string;
      min_app_version: string;
    };
  }
): ApplyResult {
  // Fail-closed: signature required
  if (!delivery.signature || !delivery.key_id) {
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "DENY",
      reason_code: 'SIGNATURE_MISSING',
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: 'SIGNATURE_MISSING', applied: false };
  }

  // Fail-closed: ts_ms required
  if (delivery.ts_ms === undefined || delivery.ts_ms === null) {
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "DENY",
      reason_code: 'CANONICAL_PAYLOAD_INVALID',
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: 'CANONICAL_PAYLOAD_INVALID', applied: false };
  }

  // Fail-closed: check expiration
  if (delivery.expires_at !== undefined && delivery.expires_at < Date.now()) {
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "DENY",
      reason_code: 'SIGNATURE_EXPIRED',
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: 'SIGNATURE_EXPIRED', applied: false };
  }

  // Verify signature
  const validation = verifyDeliveryApplySignature(
    tenantId,
    {
      model_id: delivery.model_id,
      version_id: delivery.version_id,
      artifact_id: delivery.artifact_id,
      target: delivery.target || { device_class: 'default', min_app_version: '1.0.0' },
    },
    delivery.signature,
    'ed25519',
    delivery.key_id,
    delivery.ts_ms
  );

  if (!validation.valid) {
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "DENY",
      reason_code: validation.reason_code,
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: validation.reason_code, applied: false };
  }

  // Verify sha256 matches (tamper detection)
  // In real implementation, this would check against stored artifact
  // For now, we just ensure sha256 is present
  if (!delivery.sha256) {
    appendAudit({
      ts_ms: Date.now(),
      action: "APPLY",
      result: "DENY",
      reason_code: 'SHA256_MISSING',
      key_id: delivery.key_id,
    });
    return { ok: false, reason_code: 'SHA256_MISSING', applied: false };
  }

  // Success: record ALLOW audit event
  appendAudit({
    ts_ms: Date.now(),
    action: "APPLY",
    result: "ALLOW",
    key_id: delivery.key_id,
    sha256: delivery.sha256,
  });

  return { ok: true, applied: true };
}

/**
 * Rollback artifact delivery (fail-closed on invalid signature)
 */
export function rollbackArtifact(
  tenantId: string,
  delivery: {
    sha256: string;
    signature?: string;
    key_id?: string;
    ts_ms?: number;
    model_id: string;
    version_id: string;
    artifact_id: string;
    reason_code: string;
  }
): RollbackResult {
  // Fail-closed: signature required
  if (!delivery.signature || !delivery.key_id) {
    appendAudit({
      ts_ms: Date.now(),
      action: "ROLLBACK",
      result: "DENY",
      reason_code: 'SIGNATURE_MISSING',
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: 'SIGNATURE_MISSING', rolled_back: false };
  }

  // Fail-closed: ts_ms required
  if (delivery.ts_ms === undefined || delivery.ts_ms === null) {
    appendAudit({
      ts_ms: Date.now(),
      action: "ROLLBACK",
      result: "DENY",
      reason_code: 'CANONICAL_PAYLOAD_INVALID',
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: 'CANONICAL_PAYLOAD_INVALID', rolled_back: false };
  }

  // Verify signature
  const validation = verifyDeliveryRollbackSignature(
    tenantId,
    {
      model_id: delivery.model_id,
      version_id: delivery.version_id,
      artifact_id: delivery.artifact_id,
      reason_code: delivery.reason_code,
    },
    delivery.signature,
    'ed25519',
    delivery.key_id,
    delivery.ts_ms
  );

  if (!validation.valid) {
    appendAudit({
      ts_ms: Date.now(),
      action: "ROLLBACK",
      result: "DENY",
      reason_code: validation.reason_code,
      key_id: delivery.key_id,
      sha256: delivery.sha256,
    });
    return { ok: false, reason_code: validation.reason_code, rolled_back: false };
  }

  // Success: record ALLOW audit event
  appendAudit({
    ts_ms: Date.now(),
    action: "ROLLBACK",
    result: "ALLOW",
    key_id: delivery.key_id,
    sha256: delivery.sha256,
  });

  return { ok: true, rolled_back: true };
}

