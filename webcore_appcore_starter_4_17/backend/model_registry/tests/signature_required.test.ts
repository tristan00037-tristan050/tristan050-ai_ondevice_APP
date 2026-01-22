/**
 * Model Registry Tests - Signature Required (fail-closed)
 * Verify signature validation for artifact operations
 *
 * Hard rule:
 * - tests MUST NOT contain evidence string patterns (evidence keys are emitted only by verify scripts on PASS)
 * - Jest-only (describe/it/expect)
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { createModel, createModelVersion, clearAll } from '../storage/service';
import * as artifactsApi from '../api/artifacts';
import * as signatureVerify from '../verify/signature';

// Mock signature verification
jest.mock('../verify/signature', () => ({
  verifyArtifactRegisterSignature: jest.fn(),
}));

describe('Model Registry - Signature Required', () => {
  beforeEach(() => {
    clearAll();
  });

  describe('createArtifactHandler signature validation', () => {
    it('should allow artifact register with valid signature', async () => {
      const model = createModel('tenant1', { name: 'test-model' });
      const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

      // Mock signature verification to pass
      (signatureVerify.verifyArtifactRegisterSignature as jest.Mock).mockReturnValue({
        valid: true,
      });

      const req: any = {
        params: { modelId: model.id, versionId: version!.id },
        body: {
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
          size_bytes: 1024,
          storage_ref: 's3://bucket/key',
          signature: 'valid-signature',
          sig_alg: 'ed25519',
          key_id: 'test-key-1',
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
      expect(signatureVerify.verifyArtifactRegisterSignature).toHaveBeenCalled();
    });

    it('should reject artifact register with missing signature', async () => {
      const model = createModel('tenant1', { name: 'test-model' });
      const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

      // Mock signature verification to fail (missing signature)
      (signatureVerify.verifyArtifactRegisterSignature as jest.Mock).mockReturnValue({
        valid: false,
        reason_code: 'SIGNATURE_MISSING',
        status: 400,
      });

      const req: any = {
        params: { modelId: model.id, versionId: version!.id },
        body: {
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
          size_bytes: 1024,
          storage_ref: 's3://bucket/key',
          // No signature field
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

      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          reason_code: 'SIGNATURE_MISSING',
        })
      );
    });

    it('should reject artifact register with invalid signature (tampered)', async () => {
      const model = createModel('tenant1', { name: 'test-model' });
      const version = createModelVersion('tenant1', model.id, { version: '1.0.0' });

      // Mock signature verification to fail (invalid signature)
      (signatureVerify.verifyArtifactRegisterSignature as jest.Mock).mockReturnValue({
        valid: false,
        reason_code: 'SIGNATURE_INVALID',
        status: 403,
      });

      const req: any = {
        params: { modelId: model.id, versionId: version!.id },
        body: {
          platform: 'android',
          runtime: 'tflite',
          sha256: 'abc123',
          size_bytes: 1024,
          storage_ref: 's3://bucket/key',
          signature: 'tampered-signature',
          sig_alg: 'ed25519',
          key_id: 'test-key-1',
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

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          reason_code: 'SIGNATURE_INVALID',
        })
      );
    });
  });
});

