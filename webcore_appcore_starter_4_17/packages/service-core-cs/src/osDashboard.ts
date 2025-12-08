/**
 * CS OS Dashboard 서비스
 * R8-S1: Stub 구현만 제공
 */

export interface CsOsDashboardSummary {
  tenant: string;
  ticketsTotal: number;
  ticketsOpen: number;
  ticketsResolved: number;
}

/**
 * CS OS Dashboard 요약 데이터 조회 (Stub)
 */
export async function getCsOsDashboardSummary(
  tenant: string,
): Promise<CsOsDashboardSummary> {
  // R8-S1: Stub 응답
  return {
    tenant,
    ticketsTotal: 0,
    ticketsOpen: 0,
    ticketsResolved: 0,
  };
}

