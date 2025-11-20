/**
 * 서명 이력 데이터베이스 레포지토리
 *
 * @module db/signHistory
 */
export interface SignHistory {
    reportId: string;
    tenantId: string;
    requestedBy: string;
    token: string;
    issuedAt: number;
    expiresAt: number;
    createdAt: number;
}
/**
 * 서명 이력 저장
 */
export declare function saveSignHistory(history: SignHistory): Promise<void>;
/**
 * 서명 이력 조회
 */
export declare function getSignHistory(reportId: string, tenantId: string): Promise<Array<{
    requestedBy: string;
    issuedAt: number;
    expiresAt: number;
    createdAt: number;
    tokenPreview: string;
}>>;
//# sourceMappingURL=signHistory.d.ts.map