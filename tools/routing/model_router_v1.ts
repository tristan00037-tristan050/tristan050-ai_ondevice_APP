'use strict';

// P22-AI-04 / P23-P0B-03 / P23-P1-02: ROUTING_BY_BUDGET_WITH_HYSTERESIS_V2 + ROUTING_DIGEST_SPLIT_V1 + ROUTING_BY_HARD_CONSTRAINT_AND_UTILITY_V4

import { routingDecisionDigest, routingEventId } from '../crypto/digest_v1';
import type { ThermalEnergyProfile, PowerClass } from '../device-profile/thermal_profile_v1';

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
  downgrade_path: string[];
  /** Deterministic: same decision always yields same digest (no timestamp) */
  routing_decision_digest: string;
  /** Unique per invocation: includes timestamp_ns */
  routing_event_id: string;
}

const POLICY_VERSION = 'v2';
const SCHEMA_VERSION = 1;

const PACK_IDS = ['micro_default', 'small_default'] as const;
type PackId = (typeof PACK_IDS)[number];

const FALLBACK_PACK: PackId = 'micro_default';

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
 * @deprecated — use chooseBestPack() with PackCandidate[] and RouteContext
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
    const decisionMaterial = {
      pack_id,
      reason_code,
      profile_snapshot: null as Record<string, unknown> | null,
      policy_version: POLICY_VERSION,
      schema_version: SCHEMA_VERSION,
    };
    return {
      pack_id,
      reason_code,
      downgrade_path: [],
      routing_decision_digest: routingDecisionDigest(decisionMaterial),
      routing_event_id: routingEventId({ timestamp_ns: timestamp_ns.toString(), ...decisionMaterial }),
    };
  }

  // Determine desired pack based on device constraints (downgrade priority: CPU → RAM → thermal)
  let desiredPack: PackId = 'small_default';
  let reason_code = 'BUDGET_OK';
  const downgrade_path: string[] = [];

  if (profile.cpu_usage_pct >= policy.cpu_downgrade_threshold_pct) {
    desiredPack = FALLBACK_PACK;
    reason_code = 'CPU_PRESSURE';
    downgrade_path.push('CPU');
  } else if (profile.available_ram_mb < policy.ram_downgrade_threshold_mb) {
    desiredPack = FALLBACK_PACK;
    reason_code = 'RAM_PRESSURE';
    downgrade_path.push('RAM');
  } else if (profile.thermal_state === 'hot' || profile.thermal_state === 'critical') {
    desiredPack = FALLBACK_PACK;
    reason_code = 'THERMAL_PRESSURE';
    downgrade_path.push('THERMAL');
  }

  // Hysteresis: if within cooldown window, keep current pack
  if (lastPackId !== null && desiredPack !== lastPackId) {
    const elapsed = nowMs - lastChangeMs;
    if (elapsed < policy.cooldown_ms) {
      const pack_id = lastPackId as PackId;
      const hysteresis_reason = `HYSTERESIS_COOLDOWN(${Math.round(elapsed)}ms<${policy.cooldown_ms}ms)`;
      const decisionMaterial = {
        pack_id,
        reason_code: hysteresis_reason,
        profile_snapshot: profile as Record<string, unknown>,
        policy_version: POLICY_VERSION,
        schema_version: SCHEMA_VERSION,
      };
      return {
        pack_id,
        reason_code: hysteresis_reason,
        downgrade_path,
        routing_decision_digest: routingDecisionDigest(decisionMaterial),
        routing_event_id: routingEventId({ timestamp_ns: timestamp_ns.toString(), ...decisionMaterial }),
      };
    }
  }

  const decisionMaterial = {
    pack_id: desiredPack,
    reason_code,
    profile_snapshot: profile as Record<string, unknown>,
    policy_version: POLICY_VERSION,
    schema_version: SCHEMA_VERSION,
  };

  return {
    pack_id: desiredPack,
    reason_code,
    downgrade_path,
    routing_decision_digest: routingDecisionDigest(decisionMaterial),
    routing_event_id: routingEventId({ timestamp_ns: timestamp_ns.toString(), ...decisionMaterial }),
  };
}

// ---------------------------------------------------------------------------
// P23-P1-02: ROUTING_BY_HARD_CONSTRAINT_AND_UTILITY_V4
// ---------------------------------------------------------------------------

export interface PackAssignmentPolicy {
  policy_id: string;
  target_groups: string[];
  target_device_classes: string[];
  rollout_ring: 'ring0_canary' | 'ring1_team' | 'ring2_department' | 'ring3_org';
  minimum_app_version: string;
  offline_capable_required: boolean;
  policy_digest: string;
}

export interface PackCandidate {
  // 기존
  pack_id: string;
  compiled_pack_id: string;
  status: 'verified' | 'pending_real_weights';
  fallback_rate: number;
  context_budget_tokens: number;
  power_class: PowerClass;
  q_lcb: number;
  latency_ucb_ms: number;
  rss_ucb_mb: number;
  thermal_risk_ucb: number;
  energy_ucb_per_128tok: number;
  failure_ucb: number;

  // 신규 (알고리즘팀 요청)
  logical_pack_id: string;
  tokenizer_template_digest: string;
  pack_identity_digest: string;
  backend_id: string;
  delegate_id?: string;
  delegate_partition_coverage_pct: number;
  offline_capable: boolean;

  // 기업용 신규
  device_class_id: string;
  assignment_policy?: PackAssignmentPolicy;
}

export interface RouteContext {
  // 기존
  required_context_tokens: number;
  thermal: ThermalEnergyProfile;

  // 신규 (알고리즘팀 요청)
  expected_new_tokens: number;

  // 기업용 신규
  principal_scope: 'user' | 'team' | 'department' | 'org';
  policy_digest: string;
  rollout_ring: 'ring0_canary' | 'ring1_team' | 'ring2_department' | 'ring3_org';
}

/**
 * Choose the best pack candidate using hard constraints + utility scoring.
 *
 * Hard constraints (applied in order):
 * 1. status must be 'verified'
 * 2. fallback_rate must be 0
 * 3. context_budget_tokens >= required_context_tokens
 * 4. high-power pack blocked in low_power_mode
 * 5. non-low-power pack blocked when battery is critical
 * 6. all packs blocked when thermal_state is 'critical'
 *
 * Utility score (conservative bound): q_lcb - weighted penalties
 *
 * @throws Error('NO_ELIGIBLE_PACK') if no candidate passes hard constraints
 */
export function chooseBestPack(
  candidates: PackCandidate[],
  ctx: RouteContext
): PackCandidate {
  const eligible = candidates.filter(c =>
    c.status === 'verified' &&
    c.fallback_rate === 0 &&
    c.delegate_partition_coverage_pct === 100 &&
    c.context_budget_tokens >= ctx.required_context_tokens + ctx.expected_new_tokens &&
    !(ctx.thermal.low_power_mode && c.power_class === 'high') &&
    !(ctx.thermal.battery_bucket === 'critical' && c.power_class !== 'low') &&
    !(ctx.thermal.thermal_state === 'critical')
  );

  if (eligible.length === 0) {
    throw new Error('NO_ELIGIBLE_PACK');
  }

  const score = (c: PackCandidate): number =>
    c.q_lcb
    - 0.30 * c.latency_ucb_ms
    - 0.15 * c.rss_ucb_mb
    - 0.25 * c.thermal_risk_ucb
    - 0.15 * c.energy_ucb_per_128tok
    - 0.15 * c.failure_ucb;

  return [...eligible].sort((a, b) => score(b) - score(a))[0];
}
