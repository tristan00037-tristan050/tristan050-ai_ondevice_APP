/**
 * 규칙 DSL v0
 * 기본 연산자: >, ≥, 매핑, 클램프
 *
 * @module service-core-accounting/rules
 */
/**
 * 비교 연산자 평가
 */
export function evaluateComparison(left, operator, right) {
    switch (operator) {
        case '>':
            return left > right;
        case '>=':
            return left >= right;
        case '<':
            return left < right;
        case '<=':
            return left <= right;
        case '==':
            return left === right;
        case '!=':
            return left !== right;
        default:
            return false;
    }
}
/**
 * 문자열 매핑 규칙 적용
 */
export function applyMapping(input, mappings) {
    const normalizedInput = input.toLowerCase().trim();
    for (const mapping of mappings) {
        const normalizedFrom = mapping.from.toLowerCase().trim();
        if (normalizedInput.includes(normalizedFrom) || normalizedFrom.includes(normalizedInput)) {
            return mapping.to;
        }
    }
    return null;
}
/**
 * 값 클램프 (최소/최대값 제한)
 */
export function applyClamp(value, rule) {
    let clamped = value;
    if (rule.min !== undefined && clamped < rule.min) {
        clamped = rule.min;
    }
    if (rule.max !== undefined && clamped > rule.max) {
        clamped = rule.max;
    }
    return clamped;
}
/**
 * 금액 문자열을 숫자로 변환 (부동소수점 오류 방지)
 */
export function parseAmount(amountStr) {
    // string을 직접 파싱하여 부동소수점 오류 방지
    const parts = amountStr.split('.');
    const integerPart = parseInt(parts[0] || '0', 10);
    const decimalPart = parts[1] ? parseInt(parts[1].padEnd(2, '0').substring(0, 2), 10) : 0;
    return integerPart + decimalPart / 100;
}
/**
 * 숫자를 금액 문자열로 변환 (소수점 이하 2자리)
 */
export function formatAmount(amount) {
    const integerPart = Math.floor(Math.abs(amount));
    const decimalPart = Math.round((Math.abs(amount) - integerPart) * 100);
    const sign = amount < 0 ? '-' : '';
    return `${sign}${integerPart}.${decimalPart.toString().padStart(2, '0')}`;
}
//# sourceMappingURL=rules.js.map