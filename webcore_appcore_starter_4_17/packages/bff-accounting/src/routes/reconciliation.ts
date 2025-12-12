/**
 * 대사(Reconciliation) 라우트
 * POST /v1/accounting/reconciliation/sessions
 * GET /v1/accounting/reconciliation/sessions/:id
 * POST /v1/accounting/reconciliation/sessions/:id/match
 * 
 * @module bff-accounting/routes/reconciliation
 */

import { Router, Request, Response } from 'express';
import Ajv, { type ValidateFunction } from 'ajv';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  createReconSession,
  getReconSession,
  applyReconMatch,
} from '@appcore/service-core-accounting/reconciliation.js';
import { auditLog } from '@appcore/service-core-accounting';
import { requireTenantAuth, requireRole } from '../shared/guards.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// dist/routes/에서 시작: ../../../../ = dist/ -> packages/bff-accounting/ -> packages/ -> webcore_appcore_starter_4_17/
const ROOT_DIR = join(__dirname, '../../../../');

// Ajv 인스턴스 생성
const ajv = new (Ajv as any)({ allErrors: true, strict: false });
let validateCreate: ValidateFunction | null = null;
let validateMatch: ValidateFunction | null = null;

try {
  const createSchemaPath = join(ROOT_DIR, 'contracts/accounting.reconciliation.schema.json');
  const createSchema = JSON.parse(readFileSync(createSchemaPath, 'utf8'));
  validateCreate = ajv.compile(createSchema) as ValidateFunction;
} catch (error) {
  console.warn('Failed to load reconciliation create schema:', error);
}

try {
  const matchSchemaPath = join(ROOT_DIR, 'contracts/accounting.reconciliation_match.schema.json');
  const matchSchema = JSON.parse(readFileSync(matchSchemaPath, 'utf8'));
  validateMatch = ajv.compile(matchSchema) as ValidateFunction;
} catch (error) {
  console.warn('Failed to load reconciliation match schema:', error);
}

const router = Router();

/**
 * POST /v1/accounting/reconciliation/sessions
 * 대사 세션 생성
 */
router.post('/sessions', requireTenantAuth, requireRole('operator'), async (req: Request, res: Response) => {
  try {
    const idem = req.get('Idempotency-Key');
    if (!idem) {
      return res.status(400).json({ error: 'missing_idempotency_key' });
    }
    
    const body = req.body as unknown;
    
    // 스키마 검증
    if (validateCreate && !validateCreate(body)) {
      return res.status(422).json({
        error: 'invalid_body',
        details: validateCreate.errors ?? [],
      });
    }
    
    const tenant = String(req.get('X-Tenant') ?? 'default');
    const out = await createReconSession(tenant, body as any, { idem });
    
    // 감사 이벤트
    const ctx = (req as any).ctx ?? {};
    await auditLog({
      tenant: ctx.tenant ?? 'default',
      request_id: ctx.request_id,
      idem_key: idem ?? '',
      actor: ctx.actor,
      ip: ctx.ip,
      route: req.originalUrl,
      action: 'recon_create',
      subject_type: 'recon_session',
      subject_id: out.sessionId,
      payload: body,
    });
    
    res.status(201).json(out);
  } catch (e: any) {
    console.error('Error in reconciliation session creation:', e);
    res.status(500).json({
      error: 'reconciliation_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

/**
 * GET /v1/accounting/reconciliation/sessions/:id
 * 대사 세션 조회
 */
router.get('/sessions/:id', requireTenantAuth, requireRole('operator'), async (req: Request, res: Response) => {
  try {
    const out = await getReconSession(req.params.id);
    if (!out) {
      return res.status(404).json({ error: 'not_found' });
    }
    res.status(200).json(out);
  } catch (e: any) {
    console.error('Error in reconciliation session retrieval:', e);
    res.status(500).json({
      error: 'reconciliation_get_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

/**
 * POST /v1/accounting/reconciliation/sessions/:id/match
 * 수동 매칭 적용
 */
router.post('/sessions/:id/match', requireTenantAuth, requireRole('operator'), async (req: Request, res: Response) => {
  try {
    const idem = req.get('Idempotency-Key');
    if (!idem) {
      return res.status(400).json({ error: 'missing_idempotency_key' });
    }
    
    const body = req.body as unknown;
    
    // 스키마 검증
    if (validateMatch && !validateMatch(body)) {
      return res.status(422).json({
        error: 'invalid_body',
        details: validateMatch.errors ?? [],
      });
    }
    
    const out = await applyReconMatch(
      req.params.id,
      (body as any).bank_id,
      (body as any).ledger_id
    );
    
    if (!out) {
      return res.status(404).json({ error: 'not_found' });
    }
    
    // 감사 이벤트
    const ctx = (req as any).ctx ?? {};
    await auditLog({
      tenant: ctx.tenant ?? 'default',
      request_id: ctx.request_id,
      idem_key: idem ?? '',
      actor: ctx.actor,
      ip: ctx.ip,
      route: req.originalUrl,
      action: 'recon_manual_match',
      subject_type: 'recon_session',
      subject_id: req.params.id,
      payload: body,
    });
    
    res.status(200).json(out);
  } catch (e: any) {
    console.error('Error in reconciliation manual match:', e);
    res.status(500).json({
      error: 'reconciliation_match_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

export default router;

