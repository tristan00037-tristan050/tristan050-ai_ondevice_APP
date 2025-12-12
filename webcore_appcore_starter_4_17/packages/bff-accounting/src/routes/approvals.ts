/**
 * 승인 라우트
 * POST /v1/accounting/approvals/:id
 * 
 * @module bff-accounting/routes/approvals
 */

import { Router, Request, Response } from 'express';
import Ajv, { type ValidateFunction } from 'ajv';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyApproval } from '@appcore/service-core-accounting/approvals.js';
import { auditLog } from '@appcore/service-core-accounting';
import { requireTenantAuth, requireRole } from '../shared/guards.js';

type ApprovalBody = { 
  action: 'approve' | 'reject'; 
  client_request_id: string; 
  note?: string;
  top1_selected?: boolean;  // 추천 1위가 실제 선택되었는지
  selected_rank?: number;   // 선택된 항목의 순위 (1부터 시작)
  ai_score?: number;        // 선택 항목의 추천 점수(있으면)
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// dist/routes/에서 시작: ../../../../ = dist/ -> packages/bff-accounting/ -> packages/ -> webcore_appcore_starter_4_17/
const ROOT_DIR = join(__dirname, '../../../../');

// Ajv 인스턴스 생성
const ajv = new (Ajv as any)({ allErrors: true, strict: false });
let validateApproval: ValidateFunction | null = null;

try {
  const schemaPath = join(ROOT_DIR, 'contracts/accounting.approvals.schema.json');
  const schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
  validateApproval = ajv.compile(schema as any) as ValidateFunction;
} catch (error) {
  console.warn('Failed to load approvals schema:', error);
}

const router = Router();

/**
 * POST /v1/accounting/approvals/:id
 * 승인/반려 엔드포인트
 */
router.post('/:id', requireTenantAuth, requireRole('operator'), async (req: Request, res: Response) => {
  try {
    const body = req.body as unknown;
    
    // 스키마 검증
    if (validateApproval && !validateApproval(body)) {
      return res.status(422).json({
        error: 'invalid_body',
        details: validateApproval.errors ?? [],
      });
    }
    
    const { action, client_request_id, note, top1_selected, selected_rank, ai_score } = body as ApprovalBody;
    
    // 멱등성 키 필수(헤더)
    const idem = req.get('Idempotency-Key');
    if (!idem) {
      return res.status(400).json({ error: 'missing_idempotency_key' });
    }
    
    // TODO: 멱등성 캐시 확인 (동일한 idempotencyKey로 이전 요청이 있으면 캐시된 결과 반환)
    
    const out = await applyApproval(req.params.id, action, note);
    
    // 감사 이벤트
    const ctx = (req as any).ctx ?? {};
    await auditLog({
      tenant: ctx.tenant ?? 'default',
      request_id: ctx.request_id,
      idem_key: idem ?? '',
      actor: ctx.actor,
      ip: ctx.ip,
      route: req.originalUrl,
      action: action === 'approve' ? 'approval_apply' : 'approval_reject',
      subject_type: 'report',
      subject_id: req.params.id,
      payload: { 
        note,
        ...(top1_selected !== undefined && { top1_selected }),
        ...(selected_rank !== undefined && { selected_rank }),
        ...(ai_score !== undefined && { ai_score }),
      },
    });
    
    res.status(200).json({ ...out, client_request_id });
  } catch (e: any) {
    console.error('Error in approval:', e);
    res.status(500).json({
      error: 'approval_failed',
      message: e?.message ?? 'unknown',
    });
  }
});

export default router;

