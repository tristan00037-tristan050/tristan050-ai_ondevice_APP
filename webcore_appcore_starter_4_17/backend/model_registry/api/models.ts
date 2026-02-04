/**
 * Model Registry API - Models
 * Multi-tenant: all operations scoped by tenant_id
 * RBAC: model:read, model:write
 * Audit: MODEL_CREATE
 */

import { Request, Response } from 'express';
import { auditAllow, auditDeny } from '../../control_plane/audit/hooks';
import { createModel, getModelById, listModels } from '../storage/service';
import { CreateModelRequest } from '../models/model';

/**
 * POST /api/v1/models
 * Create a new model
 * RBAC: model:write
 */
export async function createModelHandler(req: Request, res: Response): Promise<void> {
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
      'new',
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
    const request: CreateModelRequest = req.body;
    if (!request.name) {
      res.status(400).json({
        error: 'Bad Request',
        message: 'name is required',
      });
      return;
    }

    const model = createModel(context.tenant_id, request);

    // Audit ALLOW
    auditAllow(req, context, 'create', 'model', model.id);

    res.status(201).json({
      id: model.id,
      tenant_id: model.tenant_id,
      name: model.name,
      status: model.status,
      created_at: model.created_at,
      metadata: model.metadata,
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Internal Server Error',
      message: error.message || 'Failed to create model',
    });
  }
}

/**
 * GET /api/v1/models/{modelId}
 * Get model by ID
 * RBAC: model:read
 */
export async function getModelHandler(req: Request, res: Response): Promise<void> {
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
  const model = getModelById(context.tenant_id, modelId);

  if (!model) {
    res.status(404).json({
      error: 'Not Found',
      message: `Model ${modelId} not found`,
    });
    return;
  }

  res.status(200).json({
    id: model.id,
    tenant_id: model.tenant_id,
    name: model.name,
    status: model.status,
    created_at: model.created_at,
    updated_at: model.updated_at,
    metadata: model.metadata,
  });
}

/**
 * GET /api/v1/models
 * List models for tenant
 * RBAC: model:read
 */
export async function listModelsHandler(req: Request, res: Response): Promise<void> {
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
      'list',
      'Required permission: model:read'
    );
    res.status(403).json({
      error: 'Forbidden',
      message: 'Required permission: model:read',
      reason_code: 'RBAC_PERMISSION_DENIED',
    });
    return;
  }

  const models = listModels(context.tenant_id);
  res.status(200).json({
    models: models.map(m => ({
      id: m.id,
      tenant_id: m.tenant_id,
      name: m.name,
      status: m.status,
      created_at: m.created_at,
      updated_at: m.updated_at,
    })),
  });
}
