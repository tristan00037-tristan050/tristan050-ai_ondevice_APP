/**
 * 계정 매핑 규칙
 * 라인아이템 설명 → 계정 코드 매핑
 *
 * @module service-core-accounting/mapping
 */
import { applyMapping } from './rules.js';
/**
 * 기본 계정 매핑 규칙 (한국 회계 기준)
 */
const DEFAULT_ACCOUNT_MAPPINGS = [
    // 자산 계정 (1xxx)
    { from: '현금', to: '1010' },
    { from: '예금', to: '1010' },
    { from: '보통예금', to: '1010' },
    { from: '외상매출금', to: '1110' },
    { from: '미수금', to: '1130' },
    // 부채 계정 (2xxx)
    { from: '대출', to: '2010' }, // 차입금
    { from: '외상매입금', to: '2110' },
    { from: '미지급금', to: '2130' },
    // 자본 계정 (3xxx)
    { from: '자본금', to: '3010' },
    // 수익 계정 (4xxx)
    { from: '매출', to: '4010' },
    { from: '수익', to: '4010' },
    { from: '이자수익', to: '4020' },
    // 비용 계정 (5xxx, 6xxx)
    { from: '사무용품', to: '5010' }, // 사무용품비
    { from: '사무용품 구매', to: '5010' }, // 사무용품비
    { from: '택시비', to: '6010' }, // 교통비
    { from: '택시 요금', to: '6010' }, // 교통비
    { from: '주유비', to: '6010' }, // 교통비
    { from: '식대', to: '6020' }, // 접대비
    { from: '커피', to: '6020' }, // 접대비 (커피는 접대비로 분류)
    { from: '스타벅스', to: '6020' }, // 접대비
    { from: '통신비', to: '6030' }, // 통신비
    { from: '임대료', to: '6040' }, // 임대료
    { from: '급여', to: '6050' }, // 급여
    { from: '수도광열비', to: '6060' }, // 수도광열비
    { from: '보험료', to: '6070' }, // 보험료
    { from: '세금과공과', to: '6080' }, // 세금과공과
    { from: '수수료', to: '6090' }, // 수수료비용
];
/**
 * 계정 매핑 함수
 * 라인아이템 설명으로부터 계정 코드 추출
 */
export function mapAccount(description) {
    return applyMapping(description, DEFAULT_ACCOUNT_MAPPINGS);
}
/**
 * 계정 타입 판별 (차변/대변 결정)
 */
export function getAccountType(accountCode) {
    const firstDigit = accountCode.charAt(0);
    switch (firstDigit) {
        case '1':
            return 'asset'; // 자산
        case '2':
            return 'liability'; // 부채
        case '3':
            return 'equity'; // 자본
        case '4':
            return 'revenue'; // 수익
        case '5':
        case '6':
            return 'expense'; // 비용
        default:
            return 'unknown';
    }
}
/**
 * 차변/대변 결정
 * 자산/비용 증가 → 차변, 부채/자본/수익 증가 → 대변
 * amount가 음수이면 반대 처리 (감소)
 */
export function determineDebitCredit(accountType, amount) {
    const absAmount = Math.abs(amount);
    const amountStr = absAmount.toFixed(2);
    const isIncrease = amount >= 0;
    if (accountType === 'asset') {
        // 자산: 증가 → 차변, 감소 → 대변
        return isIncrease
            ? { debit: amountStr, credit: '0.00' }
            : { debit: '0.00', credit: amountStr };
    }
    else if (accountType === 'expense') {
        // 비용: 증가 → 차변
        return {
            debit: amountStr,
            credit: '0.00',
        };
    }
    else if (accountType === 'liability' || accountType === 'equity' || accountType === 'revenue') {
        // 부채/자본/수익: 증가 → 대변, 감소 → 차변
        return isIncrease
            ? { debit: '0.00', credit: amountStr }
            : { debit: amountStr, credit: '0.00' };
    }
    else {
        // 알 수 없는 경우 기본값 (자산으로 처리)
        return isIncrease
            ? { debit: amountStr, credit: '0.00' }
            : { debit: '0.00', credit: amountStr };
    }
}
//# sourceMappingURL=mapping.js.map