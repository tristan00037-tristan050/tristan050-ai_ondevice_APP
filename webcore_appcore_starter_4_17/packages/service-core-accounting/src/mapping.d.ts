/**
 * 계정 매핑 규칙
 * 라인아이템 설명 → 계정 코드 매핑
 *
 * @module service-core-accounting/mapping
 */
/**
 * 계정 매핑 함수
 * 라인아이템 설명으로부터 계정 코드 추출
 */
export declare function mapAccount(description: string): string | null;
/**
 * 계정 타입 판별 (차변/대변 결정)
 */
export declare function getAccountType(accountCode: string): 'asset' | 'liability' | 'equity' | 'revenue' | 'expense' | 'unknown';
/**
 * 차변/대변 결정
 * 자산/비용 증가 → 차변, 부채/자본/수익 증가 → 대변
 * amount가 음수이면 반대 처리 (감소)
 */
export declare function determineDebitCredit(accountType: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense' | 'unknown', amount: number): {
    debit: string;
    credit: string;
};
//# sourceMappingURL=mapping.d.ts.map