/**
 * RBAC Tests
 * Verify Fail-Closed behavior: default deny, insufficient permission => 403
 */

import { hasPermission, requirePermission } from '../auth/rbac';
import { AuthContext } from '../auth/oidc';
import { Permission } from '../models/role';

describe('RBAC Tests', () => {
  const authContext: AuthContext = {
    user_id: 'user1',
    tenant_id: 'tenant1',
    email: 'user1@example.com',
    roles: ['operator'],
  };

  describe('hasPermission', () => {
    it('should deny by default (no matching permission)', () => {
      const userRoles = [
        { permissions: ['user:read'] as Permission[] },
      ];
      const check = {
        permission: 'user:write' as Permission,
        resource_tenant_id: 'tenant1',
      };

      const result = hasPermission(authContext, check, userRoles);
      expect(result).toBe(false);
    });

    it('should allow when role has permission', () => {
      const userRoles = [
        { permissions: ['user:read', 'user:write'] as Permission[] },
      ];
      const check = {
        permission: 'user:write' as Permission,
        resource_tenant_id: 'tenant1',
      };

      const result = hasPermission(authContext, check, userRoles);
      expect(result).toBe(true);
    });

    it('should block cross-tenant access', () => {
      const userRoles = [
        { permissions: ['user:read', 'user:write'] as Permission[] },
      ];
      const check = {
        permission: 'user:read' as Permission,
        resource_tenant_id: 'tenant2', // Different tenant
      };

      const result = hasPermission(authContext, check, userRoles);
      expect(result).toBe(false);
    });
  });

  describe('requirePermission middleware', () => {
    it('should return 401 when no auth context', async () => {
      const req: any = {};
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };
      const next = jest.fn();

      const middleware = requirePermission('user:read');
      await middleware(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Unauthorized',
        message: 'Authentication required',
      });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 403 when insufficient permission', async () => {
      const req: any = {
        authContext,
        userRoles: [{ permissions: ['user:read'] as Permission[] }],
      };
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };
      const next = jest.fn();

      const middleware = requirePermission('user:write');
      await middleware(req, res, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Forbidden',
        message: 'Required permission: user:write',
      });
      expect(next).not.toHaveBeenCalled();
    });

    it('should call next when permission granted', async () => {
      const req: any = {
        authContext,
        userRoles: [{ permissions: ['user:read', 'user:write'] as Permission[] }],
      };
      const res: any = {};
      const next = jest.fn();

      const middleware = requirePermission('user:read');
      await middleware(req, res, next);

      expect(next).toHaveBeenCalled();
    });
  });
});
