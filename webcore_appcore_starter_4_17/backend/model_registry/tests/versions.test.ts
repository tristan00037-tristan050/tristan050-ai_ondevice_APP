/**
 * Model Registry Tests - Model Versions
 * Verify RBAC, audit, and multi-tenant isolation
 */

import { createModel, createModelVersion, clearAll } from '../storage/service';
import { clearAuditLogs, queryAuditLogs } from '../../control_plane/audit/service';
import * as versionsApi from '../api/versions';

describe('Model Registry - Model Versions', () => {
  beforeEach(() => {
    clearAll();
    clearAuditLogs();
  });

  describe('createModelVersionHandler', () => {
    it('should create model version with model:write permission', async () => {
      const model = createModel('tenant1', { name: 'test-model' });

      const req: any = {
        params: { modelId: model.id },
        body: { version: '1.0.0' },
        method: 'POST',
        path: `/api/v1/models/${model.id}/versions`,
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
        permissions: ['model:write', 'model:read'],
        is_super_admin: false,
      };

      await versionsApi.createModelVersionHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          version: '1.0.0',
          status: 'draft',
        })
      );

      // Verify audit log
      const logs = queryAuditLogs('tenant1', { action: 'create', resource_type: 'model' });
      expect(logs.length).toBeGreaterThan(0);
    });

    it('should return 403 when missing model:write permission', async () => {
      const model = createModel('tenant1', { name: 'test-model' });

      const req: any = {
        params: { modelId: model.id },
        body: { version: '1.0.0' },
        method: 'POST',
        path: `/api/v1/models/${model.id}/versions`,
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
        permissions: ['model:read'], // Only read, no write
        is_super_admin: false,
      };

      await versionsApi.createModelVersionHandler(req, res);

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
});

