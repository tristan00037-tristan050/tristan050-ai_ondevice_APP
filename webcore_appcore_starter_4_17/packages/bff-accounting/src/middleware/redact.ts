/**
 * PII (개인정보) 마스킹 유틸리티
 * 로그에 민감 정보가 노출되지 않도록 처리
 * 
 * @module bff-accounting/middleware/redact
 */

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const CARD = /\b(?:\d[ -]*?){13,19}\b/g;
const BIZNO = /\b\d{3}-?\d{2}-?\d{5}\b/g; // 사업자번호 패턴 단순화
const SSN = /\b\d{6}-?\d{7}\b/g;

export function redactPII(input: string): string {
  return input
    .replace(EMAIL, '[redacted-email]')
    .replace(CARD, '[redacted-card]')
    .replace(BIZNO, '[redacted-biz]')
    .replace(SSN, '[redacted-ssn]');
}

