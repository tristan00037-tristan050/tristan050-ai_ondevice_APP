/**
 * Tenants API
 * Multi-tenant IAM: Tenant management with strict isolation
 */

import { Router, Request, Response } from 'express';
import { requireAuthAndContext } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { getCallerContext, isSuperAdmin } from '../services/auth_context';
import { Tenant, CreateTenantRequest, UpdateTenantRequest } from '../models/tenant';

const router = Router();

// In-memory store (should be replaced with database in production)
const tenants: Tenant[] = [];

/**
 * GET /api/v1/iam/tenants
 * List tenants (superadmin only for all tenants, otherwise tenant-scoped)
 */
router.get(
  '/',
  requireAuthAndContext,
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only superadmin can list all tenants
    if (isSuperAdmin(context)) {
      // Superadmin: return all tenants
      const filtered = tenants.filter(t => t.status !== 'deleted');
      res.json({ tenants: filtered });
      return;
    }

    // Non-superadmin: return only own tenant
    const ownTenant = tenants.find(t => t.id === context.tenant_id && t.status !== 'deleted');
    if (!ownTenant) {
      return res.status(404).json({ error: 'Tenant not found' });
    }

    res.json({ tenants: [ownTenant] });
  }
);

/**
 * GET /api/v1/iam/tenants/me
 * Get own tenant (tenant-scoped view)
 */
router.get(
  '/me',
  requireAuthAndContext,
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only return own tenant
    const tenant = tenants.find(t => t.id === context.tenant_id && t.status !== 'deleted');
    if (!tenant) {
      return res.status(404).json({ error: 'Tenant not found' });
    }

    res.json({ tenant });
  }
);

/**
 * GET /api/v1/iam/tenants/:id
 * Get tenant by ID (tenant-scoped, cross-tenant access blocked)
 */
router.get(
  '/:id',
  requireAuthAndContext,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    // Fail-Closed: Cross-tenant access blocked (unless superadmin)
    if (!isSuperAdmin(context) && requestedId !== context.tenant_id) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'read',
        resource_type: 'tenant',
        resource_id: requestedId,
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_tenant_id: requestedId,
          caller_tenant_id: context.tenant_id,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
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
  requireAuthAndContext,
  requirePermission('tenant:write'),
  auditMiddleware('create', 'tenant'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body: CreateTenantRequest = req.body;

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
 * Update tenant (tenant-scoped, cross-tenant access blocked)
 */
router.patch(
  '/:id',
  requireAuthAndContext,
  requirePermission('tenant:write'),
  auditMiddleware('update', 'tenant'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    // Fail-Closed: Cross-tenant access blocked (unless superadmin)
    if (!isSuperAdmin(context) && requestedId !== context.tenant_id) {
      // Audit deny
      const { createAuditLog } = require('../audit/service');
      createAuditLog({
        tenant_id: context.tenant_id,
        user_id: context.user_id,
        action: 'update',
        resource_type: 'tenant',
        resource_id: requestedId,
        success: false,
        error_message: 'Cross-tenant access denied',
        metadata: {
          requested_tenant_id: requestedId,
          caller_tenant_id: context.tenant_id,
        },
      });

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
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
