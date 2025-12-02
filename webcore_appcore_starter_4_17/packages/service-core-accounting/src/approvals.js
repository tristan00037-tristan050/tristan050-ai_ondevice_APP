/**
 * 승인/반려 코어 로직
 *
 * @module service-core-accounting/approvals
 */
/**
 * 승인/반려 적용
 *
 * @param reportId - 리포트 ID
 * @param action - 승인 또는 반려
 * @param note - 메모
 * @returns 승인 결과
 */
export async function applyApproval(reportId, action, note) {
    // TODO: 저장소 연동(추후 DB/저널 기록)
    return {
        reportId,
        status: action === 'approve' ? 'APPROVED' : 'REJECTED',
        note: note ?? '',
        at: new Date().toISOString(),
    };
}
//# sourceMappingURL=approvals.js.map