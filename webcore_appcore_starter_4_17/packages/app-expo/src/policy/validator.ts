/**
 * Policy Validator (Client-side, Policy-as-Code v1)
 * Fail-Closed: 위반 시 네트워크 요청 자체를 차단
 */

export interface ValidationResult {
  pass: boolean;
  rule_id?: string;
  reason?: string;
  blocked_fields?: string[];
  missing_headers?: string[];
}

// 정책 규칙 (Policy-as-Code v1, export.yaml과 동기화)
const FORBIDDEN_FIELDS = [
  'raw_text',
  'full_content',
  'original_message',
  'token',
  'secret',
  'password',
  'api_key',
];

const MAX_LIMIT_DAYS = 90;

/**
 * Export 요청 본문 검증 (클라이언트 측)
 */
export function validateExportBody(body: any): ValidationResult {
  if (!body || typeof body !== 'object') {
    return { pass: true };
  }

  // 금지 필드 검사
  const found = FORBIDDEN_FIELDS.filter(field => field in body);
  if (found.length > 0) {
    return {
      pass: false,
      rule_id: 'export_001',
      reason: 'forbidden_fields_detected',
      blocked_fields: found,
    };
  }

  // limitDays 검사
  if (typeof body.limitDays === 'number' && body.limitDays > MAX_LIMIT_DAYS) {
    return {
      pass: false,
      rule_id: 'export_002',
      reason: 'limitDays_exceeds_max',
    };
  }

  return { pass: true };
}

/**
 * 헤더 검증 (클라이언트 측)
 */
export function validateHeaders(headers: Record<string, string>, required: string[]): ValidationResult {
  const missing = required.filter(header => !headers[header] && !headers[header.toLowerCase()]);
  if (missing.length > 0) {
    return {
      pass: false,
      rule_id: 'header_002',
      reason: 'missing_required_headers',
      missing_headers: missing,
    };
  }
  return { pass: true };
}

