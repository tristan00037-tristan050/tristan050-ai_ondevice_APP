/**
 * Export 라우트
 * POST /v1/accounting/exports/reports
 * GET /v1/accounting/exports/:jobId
 * 
 * @module bff-accounting/routes/exports
 */

import { Router, Request, Response } from 'express';
import Ajv, { type ValidateFunction } from 'ajv';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { createExportJob, getExportJob } from '@appcore/service-core-accounting/exports.js';
import { auditLog } from '@appcore/service-core-accounting';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = join(__dirname, '../../../../..');

// Ajv 인스턴스 생성
const ajv = new (Ajv as any)({ allErrors: true, strict: false });
let validateExport: ValidateFunction | null = null;

try {
  const schemaPath = join(ROOT_DIR, 'contracts/accounting.export_request.schema.json');
  const exportSchema = JSON.parse(readFileSync(schemaPath, 'utf8'));
  validateExport = ajv.compile(exportSchema) as ValidateFunction;
} catch (error) {
  console.warn('Failed to load export request schema:', error);
}

const router = Router();

/**
 * POST /v1/accounting/exports/reports
 * Export 잡 생성
 */
router.post('/reports', requireTenantAuth, requireRole('auditor'), async (req: Request, res: Response) => {
  try {
    const idem = req.get('Idempotency-Key');
    if (!idem) {
      return res.status(400).json({ error: 'missing_idempotency_key' });
    }
    
    const filters = (req.body ?? {}) as Record<string, unknown>;
    
    // 스키마 검증
    if (validateExport && !validateExport(filters)) {
      return res.status(422).json({
        error: 'invalid_body',
        details: validateExport.errors ?? [],
      });
    }
    
    // 필터 폭 제한(90일)
    if (typeof filters['limitDays'] === 'number' && filters['limitDays'] > 90) {
      return res.status(422).json({ error: 'range_too_large' });
    }
    
    const tenantId = (req as any).tenantId || req.get('X-Tenant') || 'default';
    const out = await createExportJob(tenantId, filters as any, { idem });
    
    // 감사 이벤트
    const ctx = (req as any).ctx ?? {};
    await auditLog({
      tenant: ctx.tenant ?? 'default',
      request_id: ctx.request_id,
      idem_key: idem ?? '',
      actor: ctx.actor,
      ip: ctx.ip,
      route: req.originalUrl,
      action: 'export_create',
      subject_type: 'export_job',
      subject_id: out.jobId,
      payload: filters,
    });
    
    res.status(202).json(out);
  } catch (e: any) {
    console.error('Error in export job creation:', e);
    res.status(500).json({
      error: 'export_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

/**
 * GET /v1/accounting/exports/:jobId
 * Export 잡 상태 조회
 */
router.get('/:jobId', requireTenantAuth, requireRole('auditor'), async (req: Request, res: Response) => {
  try {
    const out = await getExportJob(req.params.jobId);
    res.status(200).json(out);
  } catch (e: any) {
    console.error('Error in export job status:', e);
    res.status(500).json({
      error: 'export_status_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

export default router;
