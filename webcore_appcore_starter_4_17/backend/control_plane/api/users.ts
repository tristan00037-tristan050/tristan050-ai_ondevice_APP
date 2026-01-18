/**
 * Users API
 * Multi-tenant IAM: User management
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { User, CreateUserRequest, UpdateUserRequest } from '../models/user';

const router = Router();

// In-memory store (should be replaced with database in production)
const users: User[] = [];

/**
 * GET /api/v1/iam/users
 * List users (tenant-scoped)
 */
router.get(
  '/',
  requireAuth,
  requirePermission('user:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only show tenant's own users
    const filtered = users.filter(u => u.tenant_id === tenantId && u.status !== 'deleted');
    res.json({ users: filtered });
  }
);

/**
 * GET /api/v1/iam/users/:id
 * Get user by ID
 */
router.get(
  '/:id',
  requireAuth,
  requirePermission('user:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    const user = users.find(u => u.id === requestedId && u.status !== 'deleted');
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (user.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    res.json({ user });
  }
);

/**
 * POST /api/v1/iam/users
 * Create user
 */
router.post(
  '/',
  requireAuth,
  requirePermission('user:write'),
  auditMiddleware('create', 'user'),
  async (req: Request, res: Response) => {
    const body: CreateUserRequest = req.body;
    const authContext = (req as any).authContext;

    // Fail-Closed: Can only create users in own tenant
    if (body.tenant_id !== authContext.tenant_id) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
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
 * Update user
 */
router.patch(
  '/:id',
  requireAuth,
  requirePermission('user:write'),
  auditMiddleware('update', 'user'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    const user = users.find(u => u.id === requestedId && u.status !== 'deleted');
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (user.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
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

