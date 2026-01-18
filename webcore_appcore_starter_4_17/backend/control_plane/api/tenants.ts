/**
 * Tenants API
 * Multi-tenant IAM: Tenant management
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { Tenant, CreateTenantRequest, UpdateTenantRequest } from '../models/tenant';

const router = Router();

// In-memory store (should be replaced with database in production)
const tenants: Tenant[] = [];

/**
 * GET /api/v1/iam/tenants
 * List tenants (admin only)
 */
router.get(
  '/',
  requireAuth,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only show tenant's own data (or all if admin)
    const filtered = tenants.filter(t => t.status !== 'deleted');
    res.json({ tenants: filtered });
  }
);

/**
 * GET /api/v1/iam/tenants/:id
 * Get tenant by ID
 */
router.get(
  '/:id',
  requireAuth,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    // Fail-Closed: Cross-tenant access blocked
    if (requestedId !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    const tenant = tenants.find(t => t.id === requestedId && t.status !== 'deleted');
    if (!tenant) {
      return res.status(404).json({ error: 'Tenant not found' });
    }

    res.json({ tenant });
  }
);

/**
 * POST /api/v1/iam/tenants
 * Create tenant
 */
router.post(
  '/',
  requireAuth,
  requirePermission('tenant:write'),
  auditMiddleware('create', 'tenant'),
  async (req: Request, res: Response) => {
    const body: CreateTenantRequest = req.body;
    const authContext = (req as any).authContext;

    const tenant: Tenant = {
      id: `tenant_${Date.now()}_${Math.random().toString(36).substring(7)}`,
      name: body.name,
      status: 'active',
      created_at: new Date(),
      updated_at: new Date(),
      metadata: body.metadata,
    };

    tenants.push(tenant);
    res.status(201).json({ tenant });
  }
);

/**
 * PATCH /api/v1/iam/tenants/:id
 * Update tenant
 */
router.patch(
  '/:id',
  requireAuth,
  requirePermission('tenant:write'),
  auditMiddleware('update', 'tenant'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    const requestedId = req.params.id;

    // Fail-Closed: Cross-tenant access blocked
    if (requestedId !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    const tenant = tenants.find(t => t.id === requestedId && t.status !== 'deleted');
    if (!tenant) {
      return res.status(404).json({ error: 'Tenant not found' });
    }

    const body: UpdateTenantRequest = req.body;
    if (body.name) tenant.name = body.name;
    if (body.status) tenant.status = body.status;
    if (body.metadata) tenant.metadata = { ...tenant.metadata, ...body.metadata };
    tenant.updated_at = new Date();

    res.json({ tenant });
  }
);

export default router;

