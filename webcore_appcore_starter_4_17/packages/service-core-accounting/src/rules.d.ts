/**
 * 규칙 DSL v0
 * 기본 연산자: >, ≥, 매핑, 클램프
 *
 * @module service-core-accounting/rules
 */
export type ComparisonOperator = '>' | '>=' | '<' | '<=' | '==' | '!=';
export type MappingRule = {
    from: string;
    to: string;
};
export type ClampRule = {
    min?: number;
    max?: number;
};
/**
 * 비교 연산자 평가
 */
export declare function evaluateComparison(left: number, operator: ComparisonOperator, right: number): boolean;
/**
 * 문자열 매핑 규칙 적용
 */
export declare function applyMapping(input: string, mappings: MappingRule[]): string | null;
/**
 * 값 클램프 (최소/최대값 제한)
 */
export declare function applyClamp(value: number, rule: ClampRule): number;
/**
 * 금액 문자열을 숫자로 변환 (부동소수점 오류 방지)
 */
export declare function parseAmount(amountStr: string): number;
/**
 * 숫자를 금액 문자열로 변환 (소수점 이하 2자리)
 */
export declare function formatAmount(amount: number): string;
//# sourceMappingURL=rules.d.ts.map