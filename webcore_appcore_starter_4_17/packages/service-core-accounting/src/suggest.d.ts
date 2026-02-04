/**
 * 분개 추천 서비스
 * 규칙 DSL v0 훅 포인트 (구현은 추후 확장)
 *
 * @module service-core-accounting/suggest
 */
export interface LineItem {
    desc: string;
    amount: string;
    currency: string;
}
export interface SuggestRequest {
    items: LineItem[];
    policy_version?: string;
}
export interface Posting {
    account: string;
    debit: string;
    credit: string;
    note?: string;
}
export interface SuggestResponse {
    postings: Posting[];
    confidence: number;
    rationale: string;
    alternatives?: string[];
}
/**
 * 분개 추천 함수
 * 규칙 DSL v0 구현 (>, ≥, 매핑, 클램프)
 *
 * @param input - 라인아이템 목록
 * @param policyVersion - 정책 버전
 * @returns 추천된 분개 목록, 신뢰도, 근거
 */
export declare function suggestPostings(input: SuggestRequest, policyVersion?: string): SuggestResponse;
//# sourceMappingURL=suggest.d.ts.map