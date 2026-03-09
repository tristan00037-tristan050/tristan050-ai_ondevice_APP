'use strict';

// P25-ENT-P0-01: ENTERPRISE_SCOPE_V1

export type ScopeLevel = 'org' | 'department' | 'team' | 'user';

export interface ScopeHierarchy {
  org_scope: string;
  department_scope: string;
  team_scope: string;
  user_scope: string;
}

export interface EnterpriseScopeV1 {
  schema_version: number;
  scope_id: string;
  description: string;
  scope_hierarchy: ScopeHierarchy;
  policy_override_order: string[];
  note: string;
}

/**
 * Resolve the effective policy scope for a given principal.
 * Lower (narrower) scope overrides higher (broader) scope.
 * Override order: org_default → department_override → team_override → user_override
 */
export function resolveEffectiveScope(
  orgId: string,
  departmentId?: string,
  teamId?: string,
  userId?: string
): { scope_level: ScopeLevel; scope_key: string } {
  if (userId) {
    return { scope_level: 'user', scope_key: `user:${userId}` };
  }
  if (teamId) {
    return { scope_level: 'team', scope_key: `team:${teamId}` };
  }
  if (departmentId) {
    return { scope_level: 'department', scope_key: `department:${departmentId}` };
  }
  return { scope_level: 'org', scope_key: `org:${orgId}` };
}

/**
 * Assert that a scope hierarchy object has all 4 required levels.
 * @throws Error if any level is missing.
 */
export function assertScopeHierarchy(h: unknown): asserts h is ScopeHierarchy {
  if (!h || typeof h !== 'object') {
    throw new TypeError('ENTERPRISE_SCOPE_HIERARCHY_MISSING');
  }
  const obj = h as Record<string, unknown>;
  const required: (keyof ScopeHierarchy)[] = [
    'org_scope', 'department_scope', 'team_scope', 'user_scope',
  ];
  for (const k of required) {
    if (!obj[k] || typeof obj[k] !== 'string') {
      throw new Error(`ENTERPRISE_SCOPE_LEVEL_MISSING:${k}`);
    }
  }
}

/**
 * Assert that policy_override_order contains all 4 required entries.
 */
export function assertPolicyOverrideOrder(order: unknown): asserts order is string[] {
  if (!Array.isArray(order)) {
    throw new TypeError('ENTERPRISE_SCOPE_POLICY_OVERRIDE_ORDER_NOT_ARRAY');
  }
  const required = ['org_default', 'department_override', 'team_override', 'user_override'];
  for (const entry of required) {
    if (!order.includes(entry)) {
      throw new Error(`ENTERPRISE_SCOPE_POLICY_OVERRIDE_ORDER_MISSING:${entry}`);
    }
  }
}

/**
 * Assert a full EnterpriseScopeV1 document is valid.
 */
export function assertEnterpriseScopeV1(doc: unknown): asserts doc is EnterpriseScopeV1 {
  if (!doc || typeof doc !== 'object') {
    throw new TypeError('ENTERPRISE_SCOPE_V1_NOT_OBJECT');
  }
  const obj = doc as Record<string, unknown>;
  assertScopeHierarchy(obj['scope_hierarchy']);
  assertPolicyOverrideOrder(obj['policy_override_order']);
}
