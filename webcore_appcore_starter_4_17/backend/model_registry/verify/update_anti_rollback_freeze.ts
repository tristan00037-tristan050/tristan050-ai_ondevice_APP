/**
 * P2-2 minimal contract:
 * - Anti-rollback: incomingVersion must be >= maxSeenVersion (lower version is forbidden).
 * - Anti-freeze: expiresAtMs must be > nowMs (expired metadata is forbidden).
 *
 * Fail-closed: throws Error on violation.
 */
export function enforceAntiRollbackFreeze(input: {
  incomingVersion: number;
  maxSeenVersion: number;
  expiresAtMs: number;
  nowMs?: number;
}): void {
  const now = typeof input.nowMs === "number" ? input.nowMs : Date.now();

  if (!Number.isFinite(input.incomingVersion) || input.incomingVersion < 0) {
    throw new Error("ANTI_ROLLBACK: invalid incomingVersion");
  }
  if (!Number.isFinite(input.maxSeenVersion) || input.maxSeenVersion < 0) {
    throw new Error("ANTI_ROLLBACK: invalid maxSeenVersion");
  }
  if (!Number.isFinite(input.expiresAtMs) || input.expiresAtMs <= 0) {
    throw new Error("ANTI_FREEZE: invalid expiresAtMs");
  }

  // Anti-freeze: expired metadata must be rejected.
  if (input.expiresAtMs <= now) {
    throw new Error("ANTI_FREEZE: expired");
  }

  // Anti-rollback: lower version must be rejected.
  // Equal version is allowed to support idempotent retries.
  if (input.incomingVersion < input.maxSeenVersion) {
    throw new Error("ANTI_ROLLBACK: rollback_detected");
  }
}

