/**
 * Manual Review Queue Repository
 * 
 * @module data-pg/repos/manualReviewRepo
 */

import { pool } from '../index.js';
import type { RiskLevel } from './riskRepo.js';

export type ManualReviewStatus = 'PENDING' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED';

export interface ManualReviewItem {
  id: number;
  tenant: string;
  posting_id: string;
  risk_level: RiskLevel;
  reasons: string[];
  source: string;
  status: ManualReviewStatus;
  assignee?: string | null;
  note?: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface ManualReviewRow {
  id: number;
  tenant: string;
  posting_id: string;
  risk_level: string;
  reasons: string;  // JSONB as string
  source: string;
  status: string;
  assignee: string | null;
  note: string | null;
  created_at: Date;
  updated_at: Date;
}

/**
 * Manual Review 큐에 항목 추가
 */
export async function enqueueManualReview(input: {
  tenant: string;
  posting_id: string;
  risk_level: RiskLevel;
  reasons: string[];
  source: string;
}): Promise<ManualReviewItem> {
  const query = `
    INSERT INTO accounting_manual_review_queue (tenant, posting_id, risk_level, reasons, source, status)
    VALUES ($1, $2, $3, $4::jsonb, $5, 'PENDING')
    RETURNING id, tenant, posting_id, risk_level, reasons, source, status, assignee, note, created_at, updated_at
  `;
  
  const result = await pool.query<ManualReviewRow>(query, [
    input.tenant,
    input.posting_id,
    input.risk_level,
    JSON.stringify(input.reasons),
    input.source,
  ]);
  
  const row = result.rows[0];
  return {
    id: row.id,
    tenant: row.tenant,
    posting_id: row.posting_id,
    risk_level: row.risk_level as RiskLevel,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    source: row.source,
    status: row.status as ManualReviewStatus,
    assignee: row.assignee,
    note: row.note,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

/**
 * Manual Review 목록 조회
 */
export async function listManualReview(params: {
  tenant: string;
  status?: ManualReviewStatus;
  limit?: number;
  offset?: number;
}): Promise<ManualReviewItem[]> {
  const conditions: string[] = ['tenant = $1'];
  const args: any[] = [params.tenant];
  let argIndex = 2;
  
  if (params.status) {
    conditions.push(`status = $${argIndex}`);
    args.push(params.status);
    argIndex++;
  }
  
  const limit = params.limit || 50;
  const offset = params.offset || 0;
  
  const query = `
    SELECT id, tenant, posting_id, risk_level, reasons, source, status, assignee, note, created_at, updated_at
    FROM accounting_manual_review_queue
    WHERE ${conditions.join(' AND ')}
    ORDER BY created_at DESC
    LIMIT $${argIndex} OFFSET $${argIndex + 1}
  `;
  
  args.push(limit, offset);
  
  const result = await pool.query<ManualReviewRow>(query, args);
  
  return result.rows.map(row => ({
    id: row.id,
    tenant: row.tenant,
    posting_id: row.posting_id,
    risk_level: row.risk_level as RiskLevel,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    source: row.source,
    status: row.status as ManualReviewStatus,
    assignee: row.assignee,
    note: row.note,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }));
}

/**
 * Manual Review 상태 업데이트
 */
export async function updateManualReviewStatus(params: {
  tenant: string;
  id: number;
  status: ManualReviewStatus;
  assignee?: string;
  note?: string;
}): Promise<ManualReviewItem> {
  const updates: string[] = ['status = $3', 'updated_at = now()'];
  const args: any[] = [params.tenant, params.id, params.status];
  let argIndex = 4;
  
  if (params.assignee !== undefined) {
    updates.push(`assignee = $${argIndex}`);
    args.push(params.assignee);
    argIndex++;
  }
  
  if (params.note !== undefined) {
    updates.push(`note = $${argIndex}`);
    args.push(params.note);
    argIndex++;
  }
  
  const query = `
    UPDATE accounting_manual_review_queue
    SET ${updates.join(', ')}
    WHERE tenant = $1 AND id = $2
    RETURNING id, tenant, posting_id, risk_level, reasons, source, status, assignee, note, created_at, updated_at
  `;
  
  const result = await pool.query<ManualReviewRow>(query, args);
  
  if (result.rows.length === 0) {
    throw new Error(`Manual review item not found: id=${params.id}, tenant=${params.tenant}`);
  }
  
  const row = result.rows[0];
  return {
    id: row.id,
    tenant: row.tenant,
    posting_id: row.posting_id,
    risk_level: row.risk_level as RiskLevel,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    source: row.source,
    status: row.status as ManualReviewStatus,
    assignee: row.assignee,
    note: row.note,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

/**
 * Manual Review 항목 조회 (ID로)
 */
export async function getManualReview(tenant: string, id: number): Promise<ManualReviewItem | null> {
  const query = `
    SELECT id, tenant, posting_id, risk_level, reasons, source, status, assignee, note, created_at, updated_at
    FROM accounting_manual_review_queue
    WHERE tenant = $1 AND id = $2
  `;
  
  const result = await pool.query<ManualReviewRow>(query, [tenant, id]);
  
  if (result.rows.length === 0) {
    return null;
  }
  
  const row = result.rows[0];
  return {
    id: row.id,
    tenant: row.tenant,
    posting_id: row.posting_id,
    risk_level: row.risk_level as RiskLevel,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    source: row.source,
    status: row.status as ManualReviewStatus,
    assignee: row.assignee,
    note: row.note,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

