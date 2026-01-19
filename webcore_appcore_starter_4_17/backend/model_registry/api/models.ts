/**
 * Model Registry API
 * Signed artifact delivery with RBAC enforcement
 */

import { Router, Request, Response } from 'express';
import { requireAuthAndContext } from '../../control_plane/auth/middleware';
import { requirePermission } from '../../control_plane/auth/rbac';
import { auditMiddleware } from '../../control_plane/audit/service';
import { getCallerContext } from '../../control_plane/services/auth_context';
import {
  CreateModelRequest,
  CreateModelVersionRequest,
  DeliveryResponse,
} from '../models/model';
import {
  createModel,
  createModelVersion,
  createArtifact,
  releaseModelVersion,
  setReleasePointer,
  getDelivery,
} from '../services/storage';
import { verifyArtifact } from '../services/signing';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

const router = Router();

/**
 * POST /api/v1/models
 * Create model
 */
router.post(
  '/',
  requireAuthAndContext,
  requirePermission('model:write'),
  auditMiddleware('create', 'model'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body: CreateModelRequest = req.body;
    const model = createModel(context.tenant_id, context.user_id, {
      name: body.name,
      description: body.description,
      metadata: body.metadata,
    });

    res.status(201).json({ model });
  }
);

/**
 * POST /api/v1/models/:id/versions
 * Create model version
 */
router.post(
  '/:id/versions',
  requireAuthAndContext,
  requirePermission('model:write'),
  auditMiddleware('create', 'model_version'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const modelId = req.params.id;
    const body: CreateModelVersionRequest = req.body;

    try {
      const version = createModelVersion(modelId, context.tenant_id, context.user_id, {
        version: body.version,
        metadata: body.metadata,
      });

      res.status(201).json({ version });
    } catch (error: any) {
      res.status(404).json({ error: error.message });
    }
  }
);

/**
 * POST /api/v1/models/:id/versions/:ver/artifacts
 * Upload and sign artifact
 */
router.post(
  '/:id/versions/:ver/artifacts',
  requireAuthAndContext,
  requirePermission('model:write'),
  auditMiddleware('create', 'artifact'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const modelId = req.params.id;
    const versionStr = req.params.ver;
    const { platform, runtime, file_data } = req.body; // file_data: base64 encoded

    try {
      // Find version
      const { modelVersions } = require('../services/storage');
      const version = modelVersions.find(
        v => v.model_id === modelId && v.version === versionStr && v.tenant_id === context.tenant_id
      );
      if (!version) {
        return res.status(404).json({ error: 'Model version not found' });
      }

      // Decode and hash file
      const fileBuffer = Buffer.from(file_data, 'base64');
      const sha256 = crypto.createHash('sha256').update(fileBuffer).digest('hex');

      // Store file (simplified: in-memory for demo)
      const filePath = `/tmp/artifacts/${modelId}/${versionStr}/${platform}/${runtime}/${sha256}`;
      // In production: store in S3/object storage

      // Create artifact with signature
      const artifact = createArtifact(version.id, context.tenant_id, context.user_id, {
        platform,
        runtime,
        file_path: filePath,
        file_size: fileBuffer.length,
        sha256,
        model_id: modelId,
        version: versionStr,
      });

      res.status(201).json({ artifact });
    } catch (error: any) {
      res.status(400).json({ error: error.message });
    }
  }
);

/**
 * POST /api/v1/models/:id/versions/:ver:release
 * Release model version (immutable)
 */
router.post(
  '/:id/versions/:ver:release',
  requireAuthAndContext,
  requirePermission('model:publish'),
  auditMiddleware('update', 'model_version'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const modelId = req.params.id;
    const versionStr = req.params.ver;

    try {
      const { modelVersions } = require('../services/storage');
      const version = modelVersions.find(
        v => v.model_id === modelId && v.version === versionStr && v.tenant_id === context.tenant_id
      );
      if (!version) {
        return res.status(404).json({ error: 'Model version not found' });
      }

      const released = releaseModelVersion(version.id, context.tenant_id, context.user_id);
      res.json({ version: released });
    } catch (error: any) {
      res.status(400).json({ error: error.message });
    }
  }
);

/**
 * POST /api/v1/models/:id/versions/:ver:release-pointer
 * Set release pointer for delivery
 */
router.post(
  '/:id/versions/:ver:release-pointer',
  requireAuthAndContext,
  requirePermission('model:publish'),
  auditMiddleware('update', 'release_pointer'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const modelId = req.params.id;
    const versionStr = req.params.ver;
    const { platform, runtime, artifact_id } = req.body;

    try {
      const { modelVersions } = require('../services/storage');
      const version = modelVersions.find(
        v => v.model_id === modelId && v.version === versionStr && v.tenant_id === context.tenant_id
      );
      if (!version) {
        return res.status(404).json({ error: 'Model version not found' });
      }

      const pointer = setReleasePointer(modelId, context.tenant_id, context.user_id, {
        platform,
        runtime,
        model_version_id: version.id,
        artifact_id,
      });

      res.json({ pointer });
    } catch (error: any) {
      res.status(400).json({ error: error.message });
    }
  }
);

/**
 * GET /api/v1/models/:id/delivery
 * Get signed artifact delivery information
 */
router.get(
  '/:id/delivery',
  requireAuthAndContext,
  requirePermission('model:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const modelId = req.params.id;
    const platform = req.query.platform as string;
    const runtime = req.query.runtime as string;

    if (!platform || !runtime) {
      return res.status(400).json({ error: 'platform and runtime required' });
    }

    const delivery = getDelivery(modelId, context.tenant_id, platform, runtime);
    if (!delivery) {
      return res.status(404).json({ error: 'Delivery not found' });
    }

    // Verify signature (fail-closed)
    const isValid = verifyArtifact(
      delivery.artifact.sha256,
      modelId,
      delivery.version.version,
      platform,
      runtime,
      delivery.artifact.signature,
      delivery.signingKey.public_key
    );

    const response: DeliveryResponse = {
      model_id: modelId,
      version: delivery.version.version,
      platform,
      runtime,
      download_url: `/api/v1/models/${modelId}/artifacts/${delivery.artifact.id}/download`,
      sha256: delivery.artifact.sha256,
      signature: delivery.artifact.signature,
      key_id: delivery.artifact.key_id,
      apply_failclosed: !isValid,
      reason_code: !isValid ? 'SIGNATURE_INVALID_FAILCLOSED' : undefined,
    };

    res.json(response);
  }
);

export default router;

