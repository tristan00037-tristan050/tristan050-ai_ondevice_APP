'use strict';

// P22-AI-04: ROUTING_BY_BUDGET_WITH_HYSTERESIS_V2

import { routingDecisionDigest, routingEventId } from '../crypto/digest_v1';

export interface DeviceProfile {
  cpu_usage_pct: number;
  available_ram_mb: number;
  thermal_state: 'normal' | 'warm' | 'hot' | 'critical';
  [key: string]: unknown;
}

export interface RoutingPolicy {
  cpu_downgrade_threshold_pct: number;
  ram_downgrade_threshold_mb: number;
  cooldown_ms: number;
}

export interface RoutingResult {
  pack_id: string;
  reason_code: string;
  routing_log_digest: string;
}

const POLICY_VERSION = 'v1';
const SCHEMA_VERSION = 1;

const PACK_IDS = ['micro_default', 'small_default'] as const;
type PackId = (typeof PACK_IDS)[number];

const FALLBACK_PACK: PackId = 'micro_default';

function buildRoutingLogDigest(
  timestamp_ns: bigint,
  pack_id: string,
  reason_code: string,
  profile: DeviceProfile | null
): string {
  const decisionDigest = routingDecisionDigest({
    pack_id,
    reason_code,
    profile_snapshot: profile as Record<string, unknown> | null,
    policy_version: POLICY_VERSION,
    schema_version: SCHEMA_VERSION,
  });
  const eventId = routingEventId({
    timestamp_ns: timestamp_ns.toString(),
    pack_id,
    reason_code,
    profile_snapshot: profile as Record<string, unknown> | null,
    policy_version: POLICY_VERSION,
    schema_version: SCHEMA_VERSION,
  });
  // routing_log_digest = eventId (timestamp-bound, unique per invocation)
  // decisionDigest is deterministic for audit dedup
  void decisionDigest;
  return eventId;
}

function isValidProfile(profile: unknown): profile is DeviceProfile {
  if (!profile || typeof profile !== 'object') return false;
  const p = profile as Record<string, unknown>;
  return (
    typeof p['cpu_usage_pct'] === 'number' &&
    typeof p['available_ram_mb'] === 'number' &&
    typeof p['thermal_state'] === 'string' &&
    ['normal', 'warm', 'hot', 'critical'].includes(p['thermal_state'] as string)
  );
}

/**
 * Select a model pack based on device profile and routing policy.
 *
 * Downgrade priority: CPU → memory → thermal
 * Hysteresis: no change within cooldown_ms of last change.
 * Fail-closed: invalid/missing profile → micro_default.
 *
 * @param profile - Current device profile (null or invalid → fail-closed)
 * @param policy  - Routing thresholds and cooldown
 * @param lastPackId - Pack ID currently in use (null if none)
 * @param lastChangeMs - Wall clock ms when last pack change occurred (0 if never)
 * @param nowMs  - Current wall clock ms
 */
export function selectModelPackV2(
  profile: DeviceProfile | null | unknown,
  policy: RoutingPolicy,
  lastPackId: string | null,
  lastChangeMs: number,
  nowMs: number
): RoutingResult {
  const timestamp_ns = process.hrtime.bigint();

  // Fail-closed: invalid profile → micro_default
  if (!isValidProfile(profile)) {
    const pack_id = FALLBACK_PACK;
    const reason_code = 'PROFILE_INVALID_FAILCLOSED';
    return {
      pack_id,
      reason_code,
      routing_log_digest: buildRoutingLogDigest(timestamp_ns, pack_id, reason_code, null),
    };
  }

  // Determine desired pack based on device constraints (downgrade priority: CPU → RAM → thermal)
  let desiredPack: PackId = 'small_default';
  let reason_code = 'BUDGET_OK';

  if (profile.cpu_usage_pct >= policy.cpu_downgrade_threshold_pct) {
    desiredPack = FALLBACK_PACK;
    reason_code = 'CPU_PRESSURE';
  } else if (profile.available_ram_mb < policy.ram_downgrade_threshold_mb) {
    desiredPack = FALLBACK_PACK;
    reason_code = 'RAM_PRESSURE';
  } else if (profile.thermal_state === 'hot' || profile.thermal_state === 'critical') {
    desiredPack = FALLBACK_PACK;
    reason_code = 'THERMAL_PRESSURE';
  }

  // Hysteresis: if within cooldown window, keep current pack
  if (lastPackId !== null && desiredPack !== lastPackId) {
    const elapsed = nowMs - lastChangeMs;
    if (elapsed < policy.cooldown_ms) {
      const pack_id = lastPackId as PackId;
      const hysteresis_reason = `HYSTERESIS_COOLDOWN(${Math.round(elapsed)}ms<${policy.cooldown_ms}ms)`;
      return {
        pack_id,
        reason_code: hysteresis_reason,
        routing_log_digest: buildRoutingLogDigest(
          timestamp_ns,
          pack_id,
          hysteresis_reason,
          profile
        ),
      };
    }
  }

  return {
    pack_id: desiredPack,
    reason_code,
    routing_log_digest: buildRoutingLogDigest(timestamp_ns, desiredPack, reason_code, profile),
  };
}
