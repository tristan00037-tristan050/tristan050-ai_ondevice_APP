/**
 * CS Tickets Domain Logic
 * R9-S1: CS 티켓 리스트 및 요약 기능
 * 
 * @module service-core-cs/domain/csTickets
 */

import { exec } from '@appcore/data-pg';

export type CsTicketStatus = 'open' | 'pending' | 'closed';

export interface CsTicket {
  id: number;
  tenant: string;
  subject: string;
  status: CsTicketStatus;
  createdAt: Date;
}

export interface CsTicketSummary {
  tenant: string;
  total: number;
  byStatus: Record<CsTicketStatus, number>;
}

/**
 * CS 티켓 목록 조회
 * 
 * @param params - 조회 파라미터
 * @param params.tenant - 테넌트 ID
 * @param params.status - 상태 필터 (선택)
 * @param params.limit - 최대 조회 개수 (기본값: 20)
 * @param params.offset - 오프셋 (기본값: 0)
 * @returns 티켓 목록
 */
export async function listTickets(params: {
  tenant: string;
  status?: CsTicketStatus;
  limit?: number;
  offset?: number;
}): Promise<CsTicket[]> {
  const { tenant, status, limit = 20, offset = 0 } = params;

  let query = `
    SELECT id, tenant, subject, status, created_at
    FROM cs_tickets
    WHERE tenant = $1
  `;
  const queryParams: any[] = [tenant];

  if (status) {
    query += ` AND status = $2`;
    queryParams.push(status);
    query += ` ORDER BY created_at DESC LIMIT $3 OFFSET $4`;
    queryParams.push(limit, offset);
  } else {
    query += ` ORDER BY created_at DESC LIMIT $2 OFFSET $3`;
    queryParams.push(limit, offset);
  }

  const result = await exec(query, queryParams);

  return result.rows.map((row) => ({
    id: row.id,
    tenant: row.tenant,
    subject: row.subject,
    status: row.status as CsTicketStatus,
    createdAt: new Date(row.created_at),
  }));
}

/**
 * CS 티켓 요약 (상태별 카운트)
 * 
 * @param params - 요약 파라미터
 * @param params.tenant - 테넌트 ID
 * @param params.windowDays - 조회 기간 (일)
 * @returns 티켓 요약 정보
 */
export async function summarizeTickets(params: {
  tenant: string;
  windowDays: number;
}): Promise<CsTicketSummary> {
  const { tenant, windowDays } = params;

  const windowFrom = new Date();
  windowFrom.setDate(windowFrom.getDate() - windowDays);

  const query = `
    SELECT 
      status,
      COUNT(*) as cnt
    FROM cs_tickets
    WHERE tenant = $1
      AND created_at >= $2
    GROUP BY status
  `;

  const result = await exec(query, [tenant, windowFrom.toISOString()]);

  const byStatus: Record<CsTicketStatus, number> = {
    open: 0,
    pending: 0,
    closed: 0,
  };

  let total = 0;
  for (const row of result.rows) {
    const status = row.status as CsTicketStatus;
    const count = parseInt(row.cnt, 10);
    byStatus[status] = count;
    total += count;
  }

  return {
    tenant,
    total,
    byStatus,
  };
}

