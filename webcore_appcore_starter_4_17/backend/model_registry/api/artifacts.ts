/**
 * Model Registry API - Artifacts
 * Multi-tenant: all operations scoped by tenant_id
 * RBAC: model:read, model:write
 * Audit: ARTIFACT_REGISTER
 */

import { Request, Response } from 'express';
import { requirePermission } from '../../control_plane/auth/rbac';
import { auditAllow, auditDeny } from '../../control_plane/audit/hooks';
import { createArtifact, getArtifactById, listArtifacts } from '../storage/service';
import { CreateArtifactRequest } from '../models/artifact';

/**
 * POST /api/v1/models/{modelId}/versions/{versionId}/artifacts
 * Register a new artifact
 * RBAC: model:write
 */
export async function createArtifactHandler(req: Request, res: Response): Promise<void> {
  const context = (req as any).callerContext;
  if (!context) {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication required',
    });
    return;
  }

  // RBAC check
  if (!context.permissions.includes('model:write')) {
    auditDeny(
      req,
      context,
      'model:write',
      'model',
      req.params.artifactId || 'unknown',
      'Required permission: model:write'
    );
    res.status(403).json({
      error: 'Forbidden',
      message: 'Required permission: model:write',
      reason_code: 'RBAC_PERMISSION_DENIED',
    });
    return;
  }

  try {
    const modelId = req.params.modelId;
    const versionId = req.params.versionId;
    const request: CreateArtifactRequest = req.body;

    // Validate required fields
    if (!request.platform || !request.runtime || !request.sha256 || !request.storage_ref) {
      res.status(400).json({
        error: 'Bad Request',
        message: 'platform, runtime, sha256, and storage_ref are required',
      });
      return;
    }

    const artifact = createArtifact(context.tenant_id, modelId, versionId, request);

    if (!artifact) {
      res.status(404).json({
        error: 'Not Found',
        message: `Model ${modelId} or version ${versionId} not found`,
      });
      return;
    }

    // Audit ALLOW
    auditAllow(req, context, 'create', 'model', artifact.id);

    res.status(201).json({
      id: artifact.id,
      model_version_id: artifact.model_version_id,
      platform: artifact.platform,
      runtime: artifact.runtime,
      sha256: artifact.sha256,
      size_bytes: artifact.size_bytes,
      status: artifact.status,
      created_at: artifact.created_at,
      metadata: artifact.metadata,
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Internal Server Error',
      message: error.message || 'Failed to register artifact',
    });
  }
}

/**
 * GET /api/v1/models/{modelId}/versions/{versionId}/artifacts
 * List artifacts for a model version
 * RBAC: model:read
 */
export async function listArtifactsHandler(req: Request, res: Response): Promise<void> {
  const context = (req as any).callerContext;
  if (!context) {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication required',
    });
    return;
  }

  // RBAC check
  if (!context.permissions.includes('model:read')) {
    auditDeny(
      req,
      context,
      'model:read',
      'model',
      req.params.versionId || 'unknown',
      'Required permission: model:read'
    );
    res.status(403).json({
      error: 'Forbidden',
      message: 'Required permission: model:read',
      reason_code: 'RBAC_PERMISSION_DENIED',
    });
    return;
  }

  const modelId = req.params.modelId;
  const versionId = req.params.versionId;
  const artifacts = listArtifacts(context.tenant_id, modelId, versionId);

  res.status(200).json({
    artifacts: artifacts.map(a => ({
      id: a.id,
      model_version_id: a.model_version_id,
      platform: a.platform,
      runtime: a.runtime,
      sha256: a.sha256,
      size_bytes: a.size_bytes,
      status: a.status,
      created_at: a.created_at,
    })),
  });
}

