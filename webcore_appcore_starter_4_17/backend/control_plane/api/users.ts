/**
 * Users API
 * Multi-tenant IAM: User management with strict isolation
 */

import { Router, Request, Response } from 'express';
import { requireAuthAndContext } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { getCallerContext } from '../services/auth_context';
import { User, CreateUserRequest, UpdateUserRequest } from '../models/user';

const router = Router();

// In-memory store (should be replaced with database in production)
const users: User[] = [];

/**
 * GET /api/v1/iam/users
 * List users (tenant-scoped only)
 */
router.get(
  '/',
  requireAuthAndContext,
  requirePermission('user:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only show tenant's own users
    const filtered = users.filter(u => u.tenant_id === context.tenant_id && u.status !== 'deleted');
    res.json({ users: filtered });
  }
);

/**
 * GET /api/v1/iam/users/:id
 * Get user by ID (tenant-scoped, cross-tenant access blocked)
 */
router.get(
  '/:id',
  requireAuthAndContext,
  requirePermission('user:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    const user = users.find(u => u.id === requestedId && u.status !== 'deleted');
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (user.tenant_id !== context.tenant_id) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'read',
        resource_type: 'user',
        resource_id: requestedId,
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_user_id: requestedId,
          resource_tenant_id: user.tenant_id,
          caller_tenant_id: context.tenant_id,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
      });
    }

    res.json({ user });
  }
);

/**
 * POST /api/v1/iam/users
 * Create user (tenant-scoped)
 */
router.post(
  '/',
  requireAuthAndContext,
  requirePermission('user:write'),
  auditMiddleware('create', 'user'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body: CreateUserRequest = req.body;

    // Fail-Closed: Can only create users in own tenant
    if (body.tenant_id !== context.tenant_id) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'create',
        resource_type: 'user',
        resource_id: 'new',
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_tenant_id: body.tenant_id,
          caller_tenant_id: context.tenant_id,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
      });
    }

    const user: User = {
      id: `user_${Date.now()}_${Math.random().toString(36).substring(7)}`,
      tenant_id: body.tenant_id,
      email: body.email,
      name: body.name,
      status: 'active',
      oidc_sub: body.oidc_sub,
      created_at: new Date(),
      updated_at: new Date(),
      metadata: body.metadata,
    };

    users.push(user);
    res.status(201).json({ user });
  }
);

/**
 * PATCH /api/v1/iam/users/:id
 * Update user (tenant-scoped, cross-tenant access blocked)
 */
router.patch(
  '/:id',
  requireAuthAndContext,
  requirePermission('user:write'),
  auditMiddleware('update', 'user'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    const user = users.find(u => u.id === requestedId && u.status !== 'deleted');
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (user.tenant_id !== context.tenant_id) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'update',
        resource_type: 'user',
        resource_id: requestedId,
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_user_id: requestedId,
          resource_tenant_id: user.tenant_id,
          caller_tenant_id: context.tenant_id,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
      });
    }

    const body: UpdateUserRequest = req.body;
    if (body.email) user.email = body.email;
    if (body.name) user.name = body.name;
    if (body.status) user.status = body.status;
    if (body.metadata) user.metadata = { ...user.metadata, ...body.metadata };
    user.updated_at = new Date();

    res.json({ user });
  }
);

export default router;
