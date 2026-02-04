/**
 * Roles API
 * RBAC: Role management with strict isolation
 */

import { Router, Request, Response } from 'express';
import { requireAuthAndContext } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { auditMiddleware } from '../audit/service';
import { getCallerContext } from '../services/auth_context';
import { Role, CreateRoleRequest, UpdateRoleRequest } from '../models/role';

const router = Router();

// In-memory store (should be replaced with database in production)
const roles: Role[] = [];

/**
 * GET /api/v1/iam/roles
 * List roles (tenant-scoped only)
 */
router.get(
  '/',
  requireAuthAndContext,
  requirePermission('role:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Fail-Closed: Only show tenant's own roles
    const filtered = roles.filter(r => r.tenant_id === context.tenant_id);
    res.json({ roles: filtered });
  }
);

/**
 * GET /api/v1/iam/roles/:id
 * Get role by ID (tenant-scoped, cross-tenant access blocked)
 */
router.get(
  '/:id',
  requireAuthAndContext,
  requirePermission('role:read'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    const role = roles.find(r => r.id === requestedId);
    if (!role) {
      return res.status(404).json({ error: 'Role not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (role.tenant_id !== context.tenant_id) {
      // Audit DENY: cross-tenant access denied
      const { auditDeny } = require('../audit/hooks');
      try {
        auditDeny(
          req,
          context,
          'role:read',
          'role',
          requestedId,
          'Cross-tenant access denied'
        );
      } catch (error: any) {
        // Fail-Closed: audit write failure => request fails
        return res.status(500).json({
          error: 'Internal Server Error',
          message: 'Audit logging failed',
          reason_code: 'AUDIT_WRITE_FAILED',
        });
      }

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
      });
    }

    res.json({ role });
  }
);

/**
 * POST /api/v1/iam/roles
 * Create role (tenant-scoped)
 */
router.post(
  '/',
  requireAuthAndContext,
  requirePermission('role:write'),
  auditMiddleware('create', 'role'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body: CreateRoleRequest = req.body;

    // Fail-Closed: Can only create roles in own tenant
    if (body.tenant_id !== context.tenant_id) {
      // Audit DENY: cross-tenant access denied
      const { auditDeny } = require('../audit/hooks');
      try {
        auditDeny(
          req,
          context,
          'role:write',
          'role',
          'new',
          'Cross-tenant access denied'
        );
      } catch (error: any) {
        // Fail-Closed: audit write failure => request fails
        return res.status(500).json({
          error: 'Internal Server Error',
          message: 'Audit logging failed',
          reason_code: 'AUDIT_WRITE_FAILED',
        });
      }

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
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
 * Update role (tenant-scoped, cross-tenant access blocked)
 */
router.patch(
  '/:id',
  requireAuthAndContext,
  requirePermission('role:write'),
  auditMiddleware('update', 'role'),
  async (req: Request, res: Response) => {
    const context = getCallerContext(req);
    if (!context) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const requestedId = req.params.id;

    const role = roles.find(r => r.id === requestedId);
    if (!role) {
      return res.status(404).json({ error: 'Role not found' });
    }

    // Fail-Closed: Cross-tenant access blocked
    if (role.tenant_id !== context.tenant_id) {
      // Audit DENY: cross-tenant access denied
      const { auditDeny } = require('../audit/hooks');
      try {
        auditDeny(
          req,
          context,
          'role:write',
          'role',
          requestedId,
          'Cross-tenant access denied'
        );
      } catch (error: any) {
        // Fail-Closed: audit write failure => request fails
        return res.status(500).json({
          error: 'Internal Server Error',
          message: 'Audit logging failed',
          reason_code: 'AUDIT_WRITE_FAILED',
        });
      }

      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
        reason_code: 'TENANT_ISOLATION_VIOLATION',
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
