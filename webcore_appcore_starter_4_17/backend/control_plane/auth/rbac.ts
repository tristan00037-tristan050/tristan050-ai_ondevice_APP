/**
 * RBAC (Role-Based Access Control)
 * Deterministic permissions: same token + same state => same decision
 */

import { Permission } from '../models/role';
import { AuthContext } from './oidc';
import { CallerContext } from '../services/auth_context';

export interface PermissionCheck {
  permission: Permission;
  resource_tenant_id?: string; // For cross-tenant access blocking
}

/**
 * Check if user has permission
 * Fail-Closed: default deny, insufficient permission => false
 */
export function hasPermission(
  authContext: AuthContext,
  check: PermissionCheck,
  userRoles: Array<{ permissions: Permission[] }>
): boolean {
  // Fail-Closed: Cross-tenant access blocked
  if (check.resource_tenant_id && check.resource_tenant_id !== authContext.tenant_id) {
    return false;
  }

  // Check if any role has the required permission
  for (const role of userRoles) {
    if (role.permissions.includes(check.permission)) {
      return true;
    }
  }

  return false;
}

/**
 * Check if caller context has permission
 * Fail-Closed: default deny
 */
export function hasPermissionFromContext(
  context: CallerContext,
  permission: string
): boolean {
  // Fail-Closed: default deny
  return context.permissions.includes(permission);
}

/**
 * Require permission middleware factory
 * Fail-Closed: no permission => 403
 */
export function requirePermission(permission: Permission | string) {
  return async (
    req: any, // Express Request with callerContext
    res: any, // Express Response
    next: any // Express NextFunction
  ) => {
    const context = (req as any).callerContext;
    if (!context) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Authentication required',
      });
    }

    // Use caller context permissions (single source of truth)
    const hasAccess = hasPermissionFromContext(context, permission as string);

    if (!hasAccess) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'permission_denied',
        resource_type: 'tenant',
        resource_id: 'unknown',
        success: false,
        error_message: `Required permission: ${permission}`,
        metadata: {
          required_permission: permission,
          caller_permissions: context.permissions,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: `Required permission: ${permission}`,
        reason_code: 'RBAC_PERMISSION_DENIED',
      });
    }

    next();
  };
}

