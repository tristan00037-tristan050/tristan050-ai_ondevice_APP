/**
 * Model Registry Tests - Artifacts
 * Verify RBAC, audit, and multi-tenant isolation
 */

import { createModel, createModelVersion, createArtifact, clearAll } from '../storage/service';
import { clearAuditLogs, queryAuditLogs } from '../../control_plane/audit/service';
import * as artifactsApi from '../api/artifacts';

describe('Model Registry - Artifacts', () => {
  beforeEach(() => {
    clearAll();
    clearAuditLogs();
  });

  describe('createArtifactHandler', () => {
    it('should register artifact with model:write permission', async () => {
      const model = createModel('tenant1', { name: 'test-model' });
      const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

      const req: any = {
        params: { modelId: model.id, versionId: version!.id },
        body: {
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
          size_bytes: 1024,
          storage_ref: 's3://bucket/key',
        },
        method: 'POST',
        path: `/api/v1/models/${model.id}/versions/${version!.id}/artifacts`,
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

      await artifactsApi.createArtifactHandler(req, res);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
        })
      );

      // Verify audit log
      const logs = queryAuditLogs('tenant1', { action: 'create', resource_type: 'model' });
      expect(logs.length).toBeGreaterThan(0);
    });

    it('should return 403 when missing model:write permission', async () => {
      const model = createModel('tenant1', { name: 'test-model' });
      const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

      const req: any = {
        params: { modelId: model.id, versionId: version!.id },
        body: {
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
          size_bytes: 1024,
          storage_ref: 's3://bucket/key',
        },
        method: 'POST',
        path: `/api/v1/models/${model.id}/versions/${version!.id}/artifacts`,
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

      await artifactsApi.createArtifactHandler(req, res);

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

