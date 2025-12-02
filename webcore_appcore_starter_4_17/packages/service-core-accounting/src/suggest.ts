/**
 * 분개 추천 서비스
 * 규칙 DSL v0 훅 포인트 (구현은 추후 확장)
 * 
 * @module service-core-accounting/suggest
 */

import { mapAccount, getAccountType, determineDebitCredit } from './mapping.js';
import { parseAmount, formatAmount } from './rules.js';
import { expandAndRankCandidates } from './topn.js';

export interface LineItem {
  desc: string;
  amount: string;
  currency: string;
}

function parseAmountKRW(s: string): number {
  if (!s) return 0;
  const n = Number(String(s).replace(/[,_\s]/g, ''));
  return Number.isFinite(n) ? n : 0;
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
  alternatives?: string[]; // Top-N 후보 계정 코드 목록
}

/**
 * 분개 추천 함수
 * 규칙 DSL v0 구현 (>, ≥, 매핑, 클램프)
 * 
 * @param input - 라인아이템 목록
 * @param policyVersion - 정책 버전
 * @returns 추천된 분개 목록, 신뢰도, 근거
 */
export function suggestPostings(
  input: SuggestRequest,
  policyVersion?: string
): SuggestResponse {
  const postings: Posting[] = [];
  const rationaleParts: string[] = [];
  let totalConfidence = 0;
  
  // 각 라인아이템에 대해 분개 추천
  // 분개는 항상 차변/대변 쌍으로 생성되어야 함
  for (const item of input.items) {
    const amount = parseAmount(item.amount);
    
    // 1. 계정 매핑 (비용 계정)
    const expenseAccountCode = mapAccount(item.desc);
    
    if (!expenseAccountCode) {
      // 매핑 실패 시 기본 계정 사용 (낮은 신뢰도)
      rationaleParts.push(`"${item.desc}"에 대한 계정 매핑을 찾을 수 없어 기본 계정(5010) 사용`);
      // 비용 계정 기본값
      const expenseAccountType = getAccountType('5010');
      const { debit: expenseDebit, credit: expenseCredit } = determineDebitCredit(expenseAccountType, amount);
      
      // 차변: 비용 계정
      postings.push({
        account: '5010',
        debit: expenseDebit,
        credit: expenseCredit,
        note: item.desc,
      });
      
      // 대변: 현금 계정 (자산 감소)
      const cashAccountType = getAccountType('1010');
      const { debit: cashDebit, credit: cashCredit } = determineDebitCredit(cashAccountType, -amount);
      postings.push({
        account: '1010',
        debit: cashDebit,
        credit: cashCredit,
        note: item.desc,
      });
      
      totalConfidence += 0.3; // 낮은 신뢰도
      continue;
    }
    
    // 2. 계정 타입 판별
    const expenseAccountType = getAccountType(expenseAccountCode);
    
    // 3. 차변/대변 결정 (비용 계정)
    const { debit: expenseDebit, credit: expenseCredit } = determineDebitCredit(expenseAccountType, amount);
    
    // 4. 분개 생성 (차변: 비용 계정, 대변: 현금 계정)
    // 차변: 비용 계정
    postings.push({
      account: expenseAccountCode,
      debit: expenseDebit,
      credit: expenseCredit,
      note: item.desc,
    });
    
    // 대변: 현금 계정 (자산 감소)
    const cashAccountType = getAccountType('1010');
    const { debit: cashDebit, credit: cashCredit } = determineDebitCredit(cashAccountType, -amount);
    postings.push({
      account: '1010',
      debit: cashDebit,
      credit: cashCredit,
      note: item.desc,
    });
    
    rationaleParts.push(`"${item.desc}" → 차변: ${expenseAccountCode} (${expenseAccountType}), 대변: 1010 (현금)`);
    totalConfidence += 0.8; // 높은 신뢰도 (매핑 성공)
  }
  
  // 차변/대변 균형 확인
  // 분개는 항상 차변 합계 = 대변 합계여야 함
  // 현재 로직은 각 라인아이템마다 차변(비용)과 대변(현금)을 쌍으로 생성하므로
  // 이미 균형이 맞춰져 있어야 함
  let totalDebit = 0;
  let totalCredit = 0;
  
  for (const posting of postings) {
    totalDebit += parseAmount(posting.debit);
    totalCredit += parseAmount(posting.credit);
  }
  
  // 차변/대변 불균형 시 조정 (오차 허용 범위: 0.01)
  if (Math.abs(totalDebit - totalCredit) > 0.01) {
    const difference = totalDebit - totalCredit;
    
    if (difference > 0) {
      // 차변 초과 → 대변 계정 추가 (현금 감소)
      postings.push({
        account: '1010', // 현금 감소 (대변)
        debit: '0.00',
        credit: formatAmount(difference),
        note: '차변/대변 균형 조정 (현금 감소)',
      });
    } else {
      // 대변 초과 → 차변 계정 추가 (현금 증가)
      postings.push({
        account: '1010', // 현금 증가 (차변)
        debit: formatAmount(Math.abs(difference)),
        credit: '0.00',
        note: '차변/대변 균형 조정 (현금 증가)',
      });
    }
    
    rationaleParts.push(`차변/대변 균형 조정: ${formatAmount(Math.abs(difference))}`);
    totalConfidence *= 0.9; // 균형 조정으로 신뢰도 약간 감소
  }
  
  // 평균 신뢰도 계산
  const confidence = postings.length > 0 ? totalConfidence / postings.length : 0.0;
  
  // Top-N 후보 확장 (첫 번째 라인아이템 기준)
  let alternatives: string[] = [];
  if (input.items && input.items.length > 0) {
    const first = input.items[0];
    const desc = first.desc || '';
    const amt = parseAmountKRW(first.amount || '0');
    const ranked = expandAndRankCandidates(desc, amt, 8);
    alternatives = ranked.map(r => r.code);
  }
  
  return {
    postings,
    confidence: Math.min(1.0, confidence),
    rationale: rationaleParts.join('; '),
    alternatives,
  };
}
