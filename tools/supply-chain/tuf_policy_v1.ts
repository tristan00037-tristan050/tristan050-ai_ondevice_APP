'use strict';

// P23-P2-02: TUF_ANTI_ROLLBACK_V1

import { typedDigest } from '../crypto/digest_v1';

export interface TufMetadata {
  role: 'root' | 'targets' | 'snapshot' | 'timestamp';
  version: number;
  expires_at_utc: string;
  signed_digest_sha256: string;
}

export interface TufAntiRollbackPolicy {
  rollback_protection: boolean;
  freeze_attack_protection: boolean;
  metadata_expiry_hours_max: number;
  root_rotation_required_on_compromise: boolean;
  consistent_snapshots: boolean;
}

export interface TufVerifyResult {
  role: string;
  version: number;
  rollback_ok: boolean;
  freeze_ok: boolean;
  policy_digest_sha256: string;
  error?: string;
}

/**
 * Verify TUF metadata against anti-rollback policy.
 *
 * Fail-closed: any missing or invalid field → error result.
 * rollback_ok: new version >= current version
 * freeze_ok: expiry not exceeded (checked against nowUtc)
 *
 * @param incoming - Incoming TUF metadata to verify
 * @param current  - Currently trusted metadata (null if first time)
 * @param policy   - Anti-rollback policy
 * @param nowUtc   - Current UTC ISO string for freeze check
 */
export function verifyTufMetadata(
  incoming: TufMetadata,
  current: TufMetadata | null,
  policy: TufAntiRollbackPolicy,
  nowUtc: string
): TufVerifyResult {
  const policyDigest = typedDigest('tuf-policy', 'v1', policy);

  // Rollback check: new version must be >= current version
  let rollback_ok = true;
  if (policy.rollback_protection && current !== null) {
    if (incoming.version < current.version) {
      rollback_ok = false;
      return {
        role: incoming.role,
        version: incoming.version,
        rollback_ok,
        freeze_ok: false,
        policy_digest_sha256: policyDigest,
        error: `ROLLBACK_DETECTED: incoming version ${incoming.version} < current ${current.version}`,
      };
    }
  }

  // Freeze check: metadata must not be expired AND must not exceed policy max-expiry window
  let freeze_ok = true;
  if (policy.freeze_attack_protection) {
    const expiresAt = new Date(incoming.expires_at_utc).getTime();
    const now = new Date(nowUtc).getTime();
    if (isNaN(expiresAt) || now > expiresAt) {
      freeze_ok = false;
      return {
        role: incoming.role,
        version: incoming.version,
        rollback_ok,
        freeze_ok,
        policy_digest_sha256: policyDigest,
        error: `FREEZE_ATTACK_DETECTED: metadata expired at ${incoming.expires_at_utc}`,
      };
    }
    const maxExpiryMs = policy.metadata_expiry_hours_max * 60 * 60 * 1000;
    if (expiresAt - now > maxExpiryMs) {
      freeze_ok = false;
      return {
        role: incoming.role,
        version: incoming.version,
        rollback_ok,
        freeze_ok,
        policy_digest_sha256: policyDigest,
        error: `TUF_METADATA_EXPIRY_EXCEEDS_POLICY_MAX: expires_at=${incoming.expires_at_utc} max_hours=${policy.metadata_expiry_hours_max}`,
      };
    }
  }

  return {
    role: incoming.role,
    version: incoming.version,
    rollback_ok,
    freeze_ok,
    policy_digest_sha256: policyDigest,
  };
}

export function buildTufPolicyDigest(policy: TufAntiRollbackPolicy): string {
  return typedDigest('tuf-policy', 'v1', policy);
}
