/**
 * Telemetry Ingest API
 * OTLP (preferred) and JSON fallback
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../../control_plane/auth/middleware';
import { requirePermission } from '../../control_plane/auth/rbac';
import { ingestTelemetry, parseOTLP } from '../ingest/service';
import { IngestRequest } from '../schema/meta_only';

const router = Router();

/**
 * POST /api/v1/telemetry/ingest
 * Ingest telemetry (OTLP or JSON)
 */
router.post(
  '/ingest',
  requireAuth,
  requirePermission('tenant:write'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const contentType = req.headers['content-type'] || '';

    let request: IngestRequest | null = null;

    // Try OTLP format first (preferred)
    if (contentType.includes('application/x-protobuf') || contentType.includes('application/json')) {
      const otlpRequest = parseOTLP(req.body);
      if (otlpRequest) {
        request = otlpRequest;
      }
    }

    // Fallback to JSON format
    if (!request) {
      const body = req.body as IngestRequest;
      if (body.tenant_id && Array.isArray(body.telemetry)) {
        request = body;
      }
    }

    if (!request) {
      return res.status(400).json({
        error: 'Invalid request format',
        reason_code: 'INGEST_INVALID_FORMAT',
        message: 'Request must be OTLP or JSON format',
      });
    }

    // Fail-Closed: Ensure tenant_id matches auth context
    if (request.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        reason_code: 'INGEST_TENANT_MISMATCH',
        message: 'Request tenant_id does not match authenticated tenant',
      });
    }

    // Ingest telemetry
    const result = ingestTelemetry(request);

    if (!result.success) {
      return res.status(400).json({
        error: 'Ingest failed',
        reason_code: result.reason_code,
        message: result.message,
        ingested_count: result.ingested_count,
        rejected_count: result.rejected_count,
      });
    }

    res.status(200).json({
      success: true,
      ingested_count: result.ingested_count,
      rejected_count: result.rejected_count,
    });
  }
);

export default router;

