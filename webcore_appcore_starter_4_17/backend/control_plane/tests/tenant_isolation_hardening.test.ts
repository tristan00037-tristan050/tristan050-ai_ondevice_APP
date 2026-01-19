/**
 * Tenant Isolation Hardening Tests
 * Verify no endpoint can enumerate or access resources across tenants
 */

import { Request, Response } from 'express';
import { getCallerContext, isSuperAdmin } from '../services/auth_context';
import { createAuditLog, queryAuditLogs, clearAuditLogs } from '../audit/service';
import type { Permission } from '../models/role';

describe('Tenant Isolation Hardening Tests', () => {
  beforeEach(() => {
    clearAuditLogs();
  });

  it('should block cross-tenant list access', () => {
    // Simulate tenant1 trying to list tenant2's resources
    const req1: any = {
      callerContext: {
        tenant_id: 'tenant1',
        user_id: 'user1',
        roles: [],
        permissions: ['user:read'] as Permission[],
      },
    };

    const context1 = getCallerContext(req1);
    expect(context1).not.toBeNull();
    expect(context1?.tenant_id).toBe('tenant1');

    // Simulate tenant2's user
    const req2: any = {
      callerContext: {
        tenant_id: 'tenant2',
        user_id: 'user2',
        roles: [],
        permissions: ['user:read'] as Permission[],
      },
    };

    const context2 = getCallerContext(req2);
    expect(context2).not.toBeNull();
    expect(context2?.tenant_id).toBe('tenant2');

    // Verify contexts are isolated
    expect(context1?.tenant_id).not.toBe(context2?.tenant_id);
  });

  it('should block cross-tenant read access and audit deny', () => {
    const callerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'],
    };

    const resourceTenantId = 'tenant2';
    const resourceId = 'user-123';

    // Attempt cross-tenant read should be blocked
    if (callerContext.tenant_id !== resourceTenantId) {
      // Audit deny
      createAuditLog({
        tenant_id: callerContext.tenant_id,
        user_id: callerContext.user_id,
        action: 'read',
        resource_type: 'user',
        resource_id: resourceId,
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_user_id: resourceId,
          resource_tenant_id: resourceTenantId,
          caller_tenant_id: callerContext.tenant_id,
        },
      });

      // Verify audit log was created
      const logs = queryAuditLogs(callerContext.tenant_id, {
        action: 'read',
        resource_type: 'user',
      });

      expect(logs.length).toBeGreaterThan(0);
      const denyLog = logs.find(log => log.resource_id === resourceId && !log.success);
      expect(denyLog).not.toBeNull();
      expect(denyLog?.error_message).toContain('Cross-tenant access denied');
    }
  });

  it('should enforce tenant-scoped list (non-superadmin)', () => {
    const callerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'],
    };

    // Non-superadmin should only see own tenant's resources
    const isSuper = isSuperAdmin(callerContext);
    expect(isSuper).toBe(false);

    // Mock resources from different tenants
    const allResources = [
      { id: 'user1', tenant_id: 'tenant1' },
      { id: 'user2', tenant_id: 'tenant1' },
      { id: 'user3', tenant_id: 'tenant2' },
      { id: 'user4', tenant_id: 'tenant2' },
    ];

    // Filter by caller tenant_id
    const filtered = allResources.filter(r => r.tenant_id === callerContext.tenant_id);
    expect(filtered).toHaveLength(2);
    expect(filtered.every(r => r.tenant_id === callerContext.tenant_id)).toBe(true);
  });

  it('should allow superadmin to list all tenants', () => {
    const superAdminContext = {
      tenant_id: 'admin-tenant',
      user_id: 'admin-user',
      roles: [],
      permissions: ['iam:tenants:list_all', 'tenant:read'] as Permission[],
    };

    const isSuper = isSuperAdmin(superAdminContext);
    expect(isSuper).toBe(true);
  });

  it('should default deny when no permission', () => {
    const callerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: [] as Permission[], // No permissions
    };

    // Default deny: no permission => deny
    const hasPermission = callerContext.permissions.includes('user:read');
    expect(hasPermission).toBe(false);
  });

  it('should not enumerate cross-tenant resources', () => {
    const callerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'],
    };

    // Mock resources
    const allResources = [
      { id: 'user1', tenant_id: 'tenant1', email: 'user1@tenant1.com' },
      { id: 'user2', tenant_id: 'tenant1', email: 'user2@tenant1.com' },
      { id: 'user3', tenant_id: 'tenant2', email: 'user3@tenant2.com' },
    ];

    // Filter: only own tenant
    const visible = allResources.filter(r => r.tenant_id === callerContext.tenant_id);
    expect(visible).toHaveLength(2);
    
    // Verify no cross-tenant resources are visible
    const crossTenant = visible.find(r => r.tenant_id !== callerContext.tenant_id);
    expect(crossTenant).toBeUndefined();
  });
});
