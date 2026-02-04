/**
 * Model Registry API - Model Versions
 * Multi-tenant: all operations scoped by tenant_id
 * RBAC: model:read, model:write
 * Audit: MODEL_VERSION_CREATE
 */

import { Request, Response } from 'express';
import { requirePermission } from '../../control_plane/auth/rbac';
import { auditAllow, auditDeny } from '../../control_plane/audit/hooks';
import { createModelVersion, getModelVersionById, listModelVersions } from '../storage/service';
import { CreateModelVersionRequest } from '../models/version';

/**
 * POST /api/v1/models/{modelId}/versions
 * Create a new model version
 * RBAC: model:write
 */
export async function createModelVersionHandler(req: Request, res: Response): Promise<void> {
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
      req.params.modelId || 'unknown',
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
    const request: CreateModelVersionRequest = req.body;
    if (!request.version) {
      res.status(400).json({
        error: 'Bad Request',
        message: 'version is required',
      });
      return;
    }

    const version = createModelVersion(context.tenant_id, modelId, request);

    if (!version) {
      res.status(404).json({
        error: 'Not Found',
        message: `Model ${modelId} not found`,
      });
      return;
    }

    // Audit ALLOW
    auditAllow(req, context, 'create', 'model', version.id);

    res.status(201).json({
      id: version.id,
      model_id: version.model_id,
      version: version.version,
      status: version.status,
      created_at: version.created_at,
      metadata: version.metadata,
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Internal Server Error',
      message: error.message || 'Failed to create model version',
    });
  }
}

/**
 * GET /api/v1/models/{modelId}/versions
 * List model versions
 * RBAC: model:read
 */
export async function listModelVersionsHandler(req: Request, res: Response): Promise<void> {
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
      req.params.modelId || 'unknown',
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
  const versions = listModelVersions(context.tenant_id, modelId);

  res.status(200).json({
    versions: versions.map(v => ({
      id: v.id,
      model_id: v.model_id,
      version: v.version,
      status: v.status,
      created_at: v.created_at,
      released_at: v.released_at,
      rolled_back_at: v.rolled_back_at,
    })),
  });
}

