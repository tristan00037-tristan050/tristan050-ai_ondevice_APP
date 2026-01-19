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
 * Fail-Closed: no permission => 403 + audit DENY
 */
export function requirePermission(permission: Permission | string) {
  return async (
    req: any, // Express Request with authContext
    res: any, // Express Response
    next: any // Express NextFunction
  ) => {
    // Read ONLY req.authContext (not callerContext)
    const authContext = (req as any).authContext;
    if (!authContext) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Authentication required',
      });
    }

    // Get userRoles from req (set by auth middleware)
    const userRoles = (req as any).userRoles || [];
    
    // Check permission using authContext and userRoles
    const check = {
      permission: permission as Permission,
      resource_tenant_id: authContext.tenant_id,
    };
    const hasAccess = hasPermission(authContext, check, userRoles);

    if (!hasAccess) {
      // Audit DENY: permission check failed
      const { auditDeny } = require('../audit/hooks');
      const resourceType = inferResourceType(req.path);
      const resourceId = req.params.id || 'unknown';
      
      // Create caller context for audit (from authContext)
      const callerContext = {
        tenant_id: authContext.tenant_id,
        user_id: authContext.user_id,
        roles: authContext.roles || [],
        permissions: userRoles.flatMap((r: any) => r.permissions || []),
        is_super_admin: false,
      };

      try {
        auditDeny(
          req,
          callerContext,
          permission as string,
          resourceType,
          resourceId,
          `Required permission: ${permission}`
        );
      } catch (error: any) {
        // Fail-Closed: audit write failure => request fails
        return res.status(500).json({
          error: 'Internal Server Error',
          message: 'Audit logging failed',
          reason_code: 'AUDIT_WRITE_FAILED',
        });
      }

      return res.status(403).json({
        error: 'Forbidden',
        message: `Required permission: ${permission}`,
        reason_code: 'RBAC_PERMISSION_DENIED',
      });
    }

    next();
  };
}

/**
 * Infer resource type from path
 */
function inferResourceType(path: string): 'tenant' | 'project' | 'environment' | 'user' | 'role' | 'audit_log' {
  if (path.includes('/tenants')) return 'tenant';
  if (path.includes('/projects')) return 'project';
  if (path.includes('/environments')) return 'environment';
  if (path.includes('/users')) return 'user';
  if (path.includes('/roles')) return 'role';
  if (path.includes('/audit')) return 'audit_log';
  return 'tenant'; // Default
}

