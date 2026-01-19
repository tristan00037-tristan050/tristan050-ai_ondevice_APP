/**
 * RBAC Default Deny Tests
 * Verify default deny behavior (fail-closed)
 */

import { hasPermissionFromContext } from '../auth/rbac';
import { CallerContext } from '../services/auth_context';

describe('RBAC Default Deny Tests', () => {
  it('should deny by default when no permissions', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: [], // No permissions
    };

    const hasAccess = hasPermissionFromContext(context, 'user:read');
    expect(hasAccess).toBe(false); // Default deny
  });

  it('should deny when permission not in list', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'], // Has user:read but not user:write
    };

    const hasAccess = hasPermissionFromContext(context, 'user:write');
    expect(hasAccess).toBe(false); // Default deny
  });

  it('should allow when permission is in list', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read', 'user:write'],
    };

    const hasAccess = hasPermissionFromContext(context, 'user:read');
    expect(hasAccess).toBe(true);
  });

  it('should deny superadmin permission to non-superadmin', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'], // No iam:tenants:list_all
    };

    const hasAccess = hasPermissionFromContext(context, 'iam:tenants:list_all');
    expect(hasAccess).toBe(false); // Default deny
  });
});
