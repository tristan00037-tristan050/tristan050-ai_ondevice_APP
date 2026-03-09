'use strict';

// P25-ENT-P0-03: PACK_ASSIGNMENT_POLICY_V1

export type RolloutRing = 'ring0_canary' | 'ring1_team' | 'ring2_department' | 'ring3_org';

export interface PackAssignmentPolicyV1 {
  policy_id: string;
  target_groups: string[];
  target_device_classes: string[];
  rollout_ring: RolloutRing;
  minimum_app_version: string;
  offline_capable_required: boolean;
  policy_digest: string;
}

const VALID_ROLLOUT_RINGS: RolloutRing[] = [
  'ring0_canary',
  'ring1_team',
  'ring2_department',
  'ring3_org',
];

/**
 * Assert that a PackAssignmentPolicyV1 object has all required fields and valid values.
 * @throws Error if any required field is missing or rollout_ring is invalid.
 */
export function assertPackAssignmentPolicyV1(p: unknown): asserts p is PackAssignmentPolicyV1 {
  if (!p || typeof p !== 'object') {
    throw new TypeError('PACK_ASSIGNMENT_POLICY_V1_NOT_OBJECT');
  }
  const obj = p as Record<string, unknown>;
  const required = [
    'policy_id', 'target_groups', 'target_device_classes',
    'rollout_ring', 'minimum_app_version', 'offline_capable_required', 'policy_digest',
  ];
  for (const k of required) {
    if (obj[k] === undefined || obj[k] === null) {
      throw new Error(`PACK_ASSIGNMENT_POLICY_FIELD_MISSING:${k}`);
    }
  }
  if (!VALID_ROLLOUT_RINGS.includes(obj['rollout_ring'] as RolloutRing)) {
    throw new Error(`PACK_ASSIGNMENT_POLICY_INVALID_ROLLOUT_RING:${obj['rollout_ring']}`);
  }
  if (!Array.isArray(obj['target_groups'])) {
    throw new Error('PACK_ASSIGNMENT_POLICY_TARGET_GROUPS_NOT_ARRAY');
  }
  if (!Array.isArray(obj['target_device_classes'])) {
    throw new Error('PACK_ASSIGNMENT_POLICY_TARGET_DEVICE_CLASSES_NOT_ARRAY');
  }
  if (typeof obj['offline_capable_required'] !== 'boolean') {
    throw new Error('PACK_ASSIGNMENT_POLICY_OFFLINE_CAPABLE_REQUIRED_NOT_BOOLEAN');
  }
}

/**
 * Check whether a principal (by group_id) is covered by a policy.
 * If target_groups is empty, the policy applies to all groups (org-wide).
 */
export function isPrincipalCoveredByPolicy(
  policy: PackAssignmentPolicyV1,
  group_id?: string
): boolean {
  if (policy.target_groups.length === 0) return true;
  if (!group_id) return false;
  return policy.target_groups.includes(group_id);
}

/**
 * Check whether a device class is covered by a policy.
 * If target_device_classes is empty, the policy applies to all device classes.
 */
export function isDeviceClassCoveredByPolicy(
  policy: PackAssignmentPolicyV1,
  device_class_id: string
): boolean {
  if (policy.target_device_classes.length === 0) return true;
  return policy.target_device_classes.includes(device_class_id);
}
