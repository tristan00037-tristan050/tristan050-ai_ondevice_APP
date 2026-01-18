/**
 * RBAC (Role-Based Access Control)
 * Deterministic permissions: same token + same state => same decision
 */

import { Permission } from '../models/role';
import { AuthContext } from './oidc';

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
 * Require permission middleware factory
 * Fail-Closed: no permission => 403
 */
export function requirePermission(permission: Permission) {
  return async (
    req: any, // Express Request with authContext
    res: any, // Express Response
    next: any // Express NextFunction
  ) => {
    const authContext: AuthContext = (req as any).authContext;
    if (!authContext) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Authentication required',
      });
    }

    // Get user roles (should be loaded from DB in real implementation)
    const userRoles = (req as any).userRoles || [];

    const hasAccess = hasPermission(
      authContext,
      { permission, resource_tenant_id: (req as any).resourceTenantId },
      userRoles
    );

    if (!hasAccess) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `Required permission: ${permission}`,
      });
    }

    next();
  };
}

