/**
 * Config Distribution API
 * Versioned config with rollback and ETag support
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../../control_plane/auth/middleware';
import { requirePermission } from '../../control_plane/auth/rbac';
import { auditMiddleware } from '../../control_plane/audit/service';
import {
  createConfigVersion,
  getActiveRelease,
  getConfigVersion,
  releaseConfig,
  rollbackConfig,
  calculateETag,
} from '../storage/service';
import {
  ConfigType,
  Environment,
  CreateConfigVersionRequest,
  ReleaseConfigRequest,
  RollbackConfigRequest,
} from '../models/config';

const router = Router();

/**
 * GET /api/v1/configs/{env}/canary
 * Get active canary config (with ETag support)
 */
router.get(
  '/:env/canary',
  requireAuth,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const environment = req.params.env as Environment;
    if (!['development', 'staging', 'production'].includes(environment)) {
      return res.status(400).json({ error: 'Invalid environment' });
    }

    // Get active release
    const release = getActiveRelease('canary', environment, tenantId);
    if (!release) {
      return res.status(404).json({ error: 'No active config release found' });
    }

    // Get version content
    const version = getConfigVersion(release.version_id, tenantId);
    if (!version) {
      return res.status(404).json({ error: 'Config version not found' });
    }

    // Calculate ETag
    const etag = calculateETag(version.content);

    // Check If-None-Match header for cache validation
    const ifNoneMatch = req.headers['if-none-match'];
    if (ifNoneMatch === etag) {
      return res.status(304).end(); // Not Modified
    }

    // Set ETag header
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', 'no-cache'); // ETag-based cache validation

    res.json({
      config_type: 'canary',
      environment,
      version: version.version,
      version_id: version.id,
      content: version.content,
      released_at: release.released_at,
      etag,
    });
  }
);

/**
 * POST /api/v1/configs/{env}/canary:release
 * Release a config version
 */
router.post(
  '/:env/canary:release',
  requireAuth,
  requirePermission('tenant:write'),
  auditMiddleware('create', 'tenant'), // Using tenant as resource_type for audit
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const environment = req.params.env as Environment;
    if (!['development', 'staging', 'production'].includes(environment)) {
      return res.status(400).json({ error: 'Invalid environment' });
    }

    const body: ReleaseConfigRequest = req.body;
    const authContext = (req as any).authContext;

    // Fail-Closed: Can only release in own tenant
    if (body.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    // Fail-Closed: Config type and environment must match
    if (body.config_type !== 'canary' || body.environment !== environment) {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'Config type or environment mismatch',
      });
    }

    try {
      const release = releaseConfig({
        config_type: body.config_type,
        environment: body.environment,
        version_id: body.version_id,
        tenant_id: body.tenant_id,
        released_by: authContext.user_id,
      });

      res.status(201).json({ release });
    } catch (error: any) {
      res.status(400).json({
        error: 'Release failed',
        message: error.message,
      });
    }
  }
);

/**
 * POST /api/v1/configs/{env}/canary:rollback
 * Rollback config to previous version
 */
router.post(
  '/:env/canary:rollback',
  requireAuth,
  requirePermission('tenant:write'),
  auditMiddleware('update', 'tenant'), // Using tenant as resource_type for audit
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const environment = req.params.env as Environment;
    if (!['development', 'staging', 'production'].includes(environment)) {
      return res.status(400).json({ error: 'Invalid environment' });
    }

    const body: RollbackConfigRequest = req.body;
    const authContext = (req as any).authContext;

    // Fail-Closed: Can only rollback in own tenant
    if (body.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    // Fail-Closed: Config type and environment must match
    if (body.config_type !== 'canary' || body.environment !== environment) {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'Config type or environment mismatch',
      });
    }

    try {
      const release = rollbackConfig({
        config_type: body.config_type,
        environment: body.environment,
        to_version_id: body.to_version_id,
        tenant_id: body.tenant_id,
        released_by: authContext.user_id,
      });

      res.status(200).json({ release });
    } catch (error: any) {
      res.status(400).json({
        error: 'Rollback failed',
        message: error.message,
      });
    }
  }
);

export default router;

