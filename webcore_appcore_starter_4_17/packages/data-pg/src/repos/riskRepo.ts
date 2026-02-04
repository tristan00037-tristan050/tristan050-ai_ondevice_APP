/**
 * Risk Scores Repository
 * 
 * @module data-pg/repos/riskRepo
 */

import { pool } from '../index.js';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export interface RiskScore {
  posting_id: string;
  tenant: string;
  level: RiskLevel;
  score: number;          // 0~100
  reasons: string[];      // ["HIGH_VALUE", "LOW_CONFIDENCE", ...]
  created_at: Date;
}

export interface RiskScoreRow {
  posting_id: string;
  tenant: string;
  level: string;
  score: number;
  reasons: string;        // JSONB as string
  created_at: Date;
}

/**
 * Risk Score 저장/업데이트
 */
export async function upsertRiskScore(risk: RiskScore): Promise<void> {
  const query = `
    INSERT INTO accounting_risk_scores (posting_id, tenant, level, score, reasons, created_at)
    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
    ON CONFLICT (tenant, posting_id) 
    DO UPDATE SET
      level = EXCLUDED.level,
      score = EXCLUDED.score,
      reasons = EXCLUDED.reasons,
      created_at = EXCLUDED.created_at
  `;
  
  await pool.query(query, [
    risk.posting_id,
    risk.tenant,
    risk.level,
    risk.score,
    JSON.stringify(risk.reasons),
    risk.created_at || new Date(),
  ]);
}

/**
 * Risk Score 조회
 */
export async function getRiskScore(tenant: string, postingId: string): Promise<RiskScore | null> {
  const query = `
    SELECT posting_id, tenant, level, score, reasons, created_at
    FROM accounting_risk_scores
    WHERE tenant = $1 AND posting_id = $2
  `;
  
  const result = await pool.query<RiskScoreRow>(query, [tenant, postingId]);
  
  if (result.rows.length === 0) {
    return null;
  }
  
  const row = result.rows[0];
  return {
    posting_id: row.posting_id,
    tenant: row.tenant,
    level: row.level as RiskLevel,
    score: row.score,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    created_at: row.created_at,
  };
}

/**
 * 고위험 거래 목록 조회
 */
export async function listHighRisk(
  tenant: string,
  limit: number = 50,
  offset: number = 0
): Promise<RiskScore[]> {
  const query = `
    SELECT posting_id, tenant, level, score, reasons, created_at
    FROM accounting_risk_scores
    WHERE tenant = $1 AND level = 'HIGH'
    ORDER BY created_at DESC
    LIMIT $2 OFFSET $3
  `;
  
  const result = await pool.query<RiskScoreRow>(query, [tenant, limit, offset]);
  
  return result.rows.map(row => ({
    posting_id: row.posting_id,
    tenant: row.tenant,
    level: row.level as RiskLevel,
    score: row.score,
    reasons: typeof row.reasons === 'string' ? JSON.parse(row.reasons) : row.reasons,
    created_at: row.created_at,
  }));
}

