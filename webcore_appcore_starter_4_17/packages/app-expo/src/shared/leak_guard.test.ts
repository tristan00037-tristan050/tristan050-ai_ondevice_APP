/**
 * Leakage Firewall v1 테스트
 * 원문 일부가 그대로 포함된 출력은 FAIL
 * 충분히 추상화된 출력은 PASS
 */

import { checkLeakage, checkLeakageBatch } from './leak_guard';

describe('Leakage Firewall v1', () => {
  test('원문 일부가 그대로 포함된 출력은 FAIL (중복률 초과)', () => {
    const input = '커피 영수증 4500원 결제 완료';
    const output = '커피 영수증 4500원 결제 완료를 확인했습니다';
    
    const result = checkLeakage(input, output);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBe('DUP_RATIO_EXCEEDED');
  });

  test('원문 일부가 그대로 포함된 출력은 FAIL (연속 문자열 초과)', () => {
    const input = '커피 영수증 4500원 결제 완료';
    const output = '커피 영수증 4500원 결제 완료를 확인했습니다. 감사합니다.';
    
    const result = checkLeakage(input, output);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBeDefined();
  });

  test('충분히 추상화된 출력은 PASS', () => {
    const input = '커피 영수증 4500원 결제 완료';
    const output = '음료 구매 거래로 분류되었습니다. 금액은 4500원입니다.';
    
    const result = checkLeakage(input, output);
    expect(result.pass).toBe(true);
    expect(result.blocked).toBe(false);
  });

  test('완전히 다른 내용은 PASS', () => {
    const input = '커피 영수증 4500원';
    const output = '이 거래는 식음료 구매로 분류됩니다';
    
    const result = checkLeakage(input, output);
    expect(result.pass).toBe(true);
    expect(result.blocked).toBe(false);
  });

  test('빈 입력/출력은 PASS', () => {
    const result1 = checkLeakage('', '출력 텍스트');
    expect(result1.pass).toBe(true);
    
    const result2 = checkLeakage('입력 텍스트', '');
    expect(result2.pass).toBe(true);
    
    const result3 = checkLeakage('', '');
    expect(result3.pass).toBe(true);
  });

  test('일괄 검사: 하나라도 FAIL이면 전체 FAIL', () => {
    const input = '커피 영수증 4500원';
    const outputs = [
      { title: '음료 구매', description: '이 거래는 식음료 구매로 분류됩니다' },
      { title: '커피 영수증 4500원', description: '원문이 그대로 포함됨' },
    ];
    
    const result = checkLeakageBatch(input, outputs);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
  });

  test('일괄 검사: 모두 PASS면 전체 PASS', () => {
    const input = '커피 영수증 4500원';
    const outputs = [
      { title: '음료 구매', description: '이 거래는 식음료 구매로 분류됩니다' },
      { title: '소액 거래', description: '금액이 5000원 미만입니다' },
    ];
    
    const result = checkLeakageBatch(input, outputs);
    expect(result.pass).toBe(true);
    expect(result.blocked).toBe(false);
  });
});

