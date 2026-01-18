/**
 * Roles API
 * RBAC: Role management
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { Role, CreateRoleRequest, UpdateRoleRequest } from '../models/role';

const router = Router();

// In-memory store (should be replaced with database in production)
const roles: Role[] = [];

/**
 * GET /api/v1/iam/roles
 * List roles (tenant-scoped)
 */
router.get(
  '/',
  requireAuth,
  requirePermission('role:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only show tenant's own roles
    const filtered = roles.filter(r => r.tenant_id === tenantId);
    res.json({ roles: filtered });
  }
);

/**
 * GET /api/v1/iam/roles/:id
 * Get role by ID
 */
router.get(
  '/:id',
  requireAuth,
  requirePermission('role:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    const role = roles.find(r => r.id === requestedId);
    if (!role) {
      return res.status(404).json({ error: 'Role not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (role.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    res.json({ role });
  }
);

/**
 * POST /api/v1/iam/roles
 * Create role
 */
router.post(
  '/',
  requireAuth,
  requirePermission('role:write'),
  auditMiddleware('create', 'role'),
  async (req: Request, res: Response) => {
    const body: CreateRoleRequest = req.body;
    const authContext = (req as any).authContext;

    // Fail-Closed: Can only create roles in own tenant
    if (body.tenant_id !== authContext.tenant_id) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    const role: Role = {
      id: `role_${Date.now()}_${Math.random().toString(36).substring(7)}`,
      tenant_id: body.tenant_id,
      name: body.name,
      description: body.description,
      permissions: body.permissions,
      created_at: new Date(),
      updated_at: new Date(),
    };

    roles.push(role);
    res.status(201).json({ role });
  }
);

/**
 * PATCH /api/v1/iam/roles/:id
 * Update role
 */
router.patch(
  '/:id',
  requireAuth,
  requirePermission('role:write'),
  auditMiddleware('update', 'role'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    const role = roles.find(r => r.id === requestedId);
    if (!role) {
      return res.status(404).json({ error: 'Role not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (role.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    const body: UpdateRoleRequest = req.body;
    if (body.name) role.name = body.name;
    if (body.description !== undefined) role.description = body.description;
    if (body.permissions) role.permissions = body.permissions;
    role.updated_at = new Date();

    res.json({ role });
  }
);

export default router;

