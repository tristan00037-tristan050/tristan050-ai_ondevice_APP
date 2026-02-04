/**
 * 승인/반려 코어 로직
 * 
 * @module service-core-accounting/approvals
 */

export type ApprovalAction = 'approve' | 'reject';

export interface ApprovalResult {
  reportId: string;
  status: 'APPROVED' | 'REJECTED';
  note: string;
  at: string;
}

/**
 * 승인/반려 적용
 * 
 * @param reportId - 리포트 ID
 * @param action - 승인 또는 반려
 * @param note - 메모
 * @returns 승인 결과
 */
export async function applyApproval(
  reportId: string,
  action: ApprovalAction,
  note?: string
): Promise<ApprovalResult> {
  // TODO: 저장소 연동(추후 DB/저널 기록)
  return {
    reportId,
    status: action === 'approve' ? 'APPROVED' : 'REJECTED',
    note: note ?? '',
    at: new Date().toISOString(),
  };
}


