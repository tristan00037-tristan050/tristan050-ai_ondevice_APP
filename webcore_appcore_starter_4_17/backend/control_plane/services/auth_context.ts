/**
 * Auth Context Service
 * Single source of truth for caller context
 */

import { Request } from 'express';
import { AuthContext } from '../auth/oidc';

export interface CallerContext {
  tenant_id: string;
  user_id: string;
  roles: string[];
  permissions: string[];
}

/**
 * Extract caller context from request
 * Single source of truth: req.auth = { tenant_id, user_id, roles, permissions }
 */
export function getCallerContext(req: Request): CallerContext | null {
  const authContext: AuthContext | undefined = (req as any).authContext;
  if (!authContext) {
    return null;
  }

  // Get user roles and permissions (should be loaded from DB in real implementation)
  const userRoles = (req as any).userRoles || [];
  const permissions: string[] = [];
  
  // Extract permissions from roles
  for (const role of userRoles) {
    if (role.permissions && Array.isArray(role.permissions)) {
      permissions.push(...role.permissions);
    }
  }

  return {
    tenant_id: authContext.tenant_id,
    user_id: authContext.user_id,
    roles: authContext.roles || [],
    permissions,
  };
}

/**
 * Require caller context middleware
 * Fail-Closed: no context => 401
 */
export function requireCallerContext(
  req: Request,
  res: any,
  next: any
): void {
  const context = getCallerContext(req);
  if (!context) {
    return res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication required',
    });
  }

  (req as any).callerContext = context;
  next();
}

/**
 * Check if caller has permission
 * Fail-Closed: default deny
 */
export function hasPermission(context: CallerContext, permission: string): boolean {
  return context.permissions.includes(permission);
}

/**
 * Check if caller is superadmin
 * Superadmin has 'iam:tenants:list_all' permission
 */
export function isSuperAdmin(context: CallerContext): boolean {
  return hasPermission(context, 'iam:tenants:list_all');
}

