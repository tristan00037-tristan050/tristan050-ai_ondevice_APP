/**
 * Model Registry Tests - Models
 * Verify RBAC, audit, and multi-tenant isolation
 */

import { Request, Response } from 'express';
import { createModel, getModelById, listModels, clearAll } from '../storage/service';
import { getCallerContext } from '../../control_plane/services/auth_context';
import { queryAuditLogs, clearAuditLogs } from '../../control_plane/audit/service';
import * as modelsApi from '../api/models';

describe('Model Registry - Models', () => {
  beforeEach(() => {
    clearAll();
    clearAuditLogs();
  });

  describe('createModelHandler', () => {
    it('should create model with model:write permission', async () => {
      const req: any = {
        body: { name: 'test-model' },
        params: {},
        method: 'POST',
        path: '/api/v1/models',
        ip: '127.0.0.1',
        connection: { remoteAddress: '127.0.0.1' },
        headers: {},
      };
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };

      // Mock caller context with model:write permission
      (req as any).callerContext = {
        tenant_id: 'tenant1',
        user_id: 'user1',
        roles: [],
        permissions: ['model:write', 'model:read'],
        is_super_admin: false,
      };

      await modelsApi.createModelHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'test-model',
          tenant_id: 'tenant1',
        })
      );

      // Verify audit log
      const logs = queryAuditLogs('tenant1', { action: 'create', resource_type: 'model' });
      expect(logs.length).toBeGreaterThan(0);
    });

    it('should return 403 when missing model:write permission', async () => {
      const req: any = {
        body: { name: 'test-model' },
        params: {},
        method: 'POST',
        path: '/api/v1/models',
        ip: '127.0.0.1',
        connection: { remoteAddress: '127.0.0.1' },
        headers: {},
      };
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };

      // Mock caller context without model:write permission
      (req as any).callerContext = {
        tenant_id: 'tenant1',
        user_id: 'user1',
        roles: [],
        permissions: ['model:read'], // Only read, no write
        is_super_admin: false,
      };

      await modelsApi.createModelHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Forbidden',
          reason_code: 'RBAC_PERMISSION_DENIED',
        })
      );

      // Verify audit deny log
      const logs = queryAuditLogs('tenant1', { action: 'permission_denied' });
      expect(logs.length).toBeGreaterThan(0);
    });
  });

  describe('getModelHandler', () => {
    it('should return model with model:read permission', async () => {
      // Create a model first
      const model = createModel('tenant1', { name: 'test-model' });

      const req: any = {
        params: { modelId: model.id },
        method: 'GET',
        path: `/api/v1/models/${model.id}`,
        ip: '127.0.0.1',
        connection: { remoteAddress: '127.0.0.1' },
        headers: {},
      };
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };

      (req as any).callerContext = {
        tenant_id: 'tenant1',
        user_id: 'user1',
        roles: [],
        permissions: ['model:read'],
        is_super_admin: false,
      };

      await modelsApi.getModelHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          id: model.id,
          name: 'test-model',
        })
      );
    });

    it('should return 404 for cross-tenant access', async () => {
      // Create a model for tenant1
      const model = createModel('tenant1', { name: 'test-model' });

      const req: any = {
        params: { modelId: model.id },
        method: 'GET',
        path: `/api/v1/models/${model.id}`,
        ip: '127.0.0.1',
        connection: { remoteAddress: '127.0.0.1' },
        headers: {},
      };
      const res: any = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn(),
      };

      // Try to access from tenant2
      (req as any).callerContext = {
        tenant_id: 'tenant2',
        user_id: 'user2',
        roles: [],
        permissions: ['model:read'],
        is_super_admin: false,
      };

      await modelsApi.getModelHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });
  });
});

