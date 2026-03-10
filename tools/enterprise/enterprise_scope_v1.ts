'use strict';

// P25-ENT-P0-01 / AI-P3-04: ENTERPRISE_SCOPE_V1 + POLICY_CONFLICT_ENGINE_V1

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

// ---------------------------------------------------------------------------
// AI-P3-04: POLICY_CONFLICT_ENGINE_V1 — 권한 escalation 차단 엔진
// ---------------------------------------------------------------------------

export interface ScopedPolicy {
  scope_level: ScopeLevel;
  scope_key: string;
  allowed_tools: string[];
  denied_tools: string[];
  allowed_pack_ids: string[];
  data_tier: 'public' | 'internal' | 'restricted';
  rollout_ring?: string;
  policy_digest: string;
  overrides?: Partial<Record<string, unknown>>;
}

export interface PolicyConflict {
  type:
    | 'PRIVILEGE_ESCALATION'
    | 'TOOL_PERMISSION_CONFLICT'
    | 'PACK_ASSIGNMENT_CONFLICT'
    | 'DATA_TIER_CONFLICT'
    | 'ROLLOUT_RING_CONFLICT';
  field: string;
  wide_scope: ScopeLevel;
  narrow_scope: ScopeLevel;
  detail: string;
}

/**
 * Resolve the effective policy by applying narrower scopes over wider scopes.
 * Blocks privilege escalation: narrower scope cannot grant more than wider scope.
 *
 * Scope order (wide → narrow): org → department → team → user
 *
 * Escalation checks:
 * - Tool: narrower scope cannot add tools not in wider scope → POLICY_PRIVILEGE_ESCALATION
 * - Pack: narrower scope cannot add pack_ids not in wider scope → POLICY_PACK_ESCALATION
 * - Data tier: narrower scope cannot raise data_tier rank → POLICY_DATA_TIER_ESCALATION
 *
 * @throws Error on any privilege escalation attempt.
 */
export function resolveEffectivePolicy(
  policies: ScopedPolicy[]
): ScopedPolicy {
  const order: ScopeLevel[] = ['org', 'department', 'team', 'user'];
  const sorted = [...policies].sort(
    (a, b) => order.indexOf(a.scope_level) - order.indexOf(b.scope_level)
  );

  let effective: ScopedPolicy | null = null;

  for (const p of sorted) {
    if (!effective) {
      effective = { ...p };
      continue;
    }

    // Tool 권한 escalation 차단
    const escalatedTools = p.allowed_tools.filter(
      t => !effective!.allowed_tools.includes(t)
    );
    if (escalatedTools.length > 0) {
      throw new Error(
        `POLICY_PRIVILEGE_ESCALATION:${p.scope_level}:${escalatedTools.join(',')}`
      );
    }

    // Pack 권한 escalation 차단
    const escalatedPacks = p.allowed_pack_ids.filter(
      x => !effective!.allowed_pack_ids.includes(x)
    );
    if (escalatedPacks.length > 0) {
      throw new Error(
        `POLICY_PACK_ESCALATION:${p.scope_level}:${escalatedPacks.join(',')}`
      );
    }

    // Data tier escalation 차단
    const dataTierRank: Record<string, number> = {
      public: 0, internal: 1, restricted: 2,
    };
    if (dataTierRank[p.data_tier] > dataTierRank[effective.data_tier]) {
      throw new Error(
        `POLICY_DATA_TIER_ESCALATION:${p.scope_level}:${p.data_tier}`
      );
    }

    effective = {
      ...effective,
      ...p,
      allowed_tools: effective.allowed_tools.filter(
        t => !p.denied_tools.includes(t)
      ),
      allowed_pack_ids: effective.allowed_pack_ids.filter(
        x => p.allowed_pack_ids.includes(x)
      ),
    };
  }

  if (!effective) throw new Error('ENTERPRISE_POLICY_NOT_FOUND');
  return effective;
}

/**
 * Assert that no policy conflicts exist across the given policy set.
 * Delegates to resolveEffectivePolicy — throws on any escalation.
 */
export function assertNoPolicyConflicts(
  policies: ScopedPolicy[]
): void {
  // resolveEffectivePolicy 가 throw 하면 conflict 존재
  resolveEffectivePolicy(policies);
}
