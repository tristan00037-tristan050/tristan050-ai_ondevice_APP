/**
 * Policy Validator (Policy-as-Code v1)
 * Fail-Closed: 위반 시 즉시 차단
 */

import { Request } from 'express';
import { PolicyRule, getExportPolicy, getHeadersPolicy, getMetaOnlyPolicy } from './loader.js';

export interface ValidationResult {
  pass: boolean;
  rule_id?: string;
  reason?: string;
  blocked_fields?: string[];
  missing_headers?: string[];
}

/**
 * Export 요청 본문 검증
 */
export function validateExportBody(body: any): ValidationResult {
  const policy = getExportPolicy();
  if (!policy) {
    return { pass: true }; // 정책 없으면 통과 (기존 동작 유지)
  }

  // 금지 필드 검사
  for (const rule of policy.rules) {
    if (rule.forbidden_fields) {
      const found = rule.forbidden_fields.filter(field => {
        return body && typeof body === 'object' && field in body;
      });
      if (found.length > 0) {
        return {
          pass: false,
          rule_id: rule.id,
          reason: `forbidden_fields_detected`,
          blocked_fields: found,
        };
      }
    }

    // limitDays 검사
    if (rule.max_limit_days && typeof body?.limitDays === 'number') {
      if (body.limitDays > rule.max_limit_days) {
        return {
          pass: false,
          rule_id: rule.id,
          reason: `limitDays_exceeds_max`,
        };
      }
    }
  }

  return { pass: true };
}

/**
 * 헤더 검증
 */
export function validateHeaders(req: Request, ruleId?: string): ValidationResult {
  const policy = getHeadersPolicy();
  if (!policy) {
    return { pass: true };
  }

  const rule = ruleId 
    ? policy.rules.find(r => r.id === ruleId)
    : policy.rules.find(r => r.required_headers);

  if (!rule || !rule.required_headers) {
    return { pass: true };
  }

  const missing = rule.required_headers.filter(header => !req.get(header));
  if (missing.length > 0) {
    return {
      pass: false,
      rule_id: rule.id,
      reason: `missing_required_headers`,
      missing_headers: missing,
    };
  }

  return { pass: true };
}

/**
 * 감사 로그 meta-only 검증
 */
export function validateAuditPayload(payload: any): ValidationResult {
  const policy = getMetaOnlyPolicy();
  if (!policy) {
    return { pass: true };
  }

  for (const rule of policy.rules) {
    if (rule.forbidden_fields) {
      const found = rule.forbidden_fields.filter(field => {
        return payload && typeof payload === 'object' && field in payload;
      });
      if (found.length > 0) {
        return {
          pass: false,
          rule_id: rule.id,
          reason: `forbidden_fields_in_audit`,
          blocked_fields: found,
        };
      }
    }
  }

  return { pass: true };
}

/**
 * 감사 로그에서 meta-only 필드만 추출
 */
export function extractMetaOnlyAudit(payload: any): Record<string, unknown> {
  const policy = getMetaOnlyPolicy();
  if (!policy) {
    return payload; // 정책 없으면 원본 반환
  }

  const allowedFields = policy.rules
    .flatMap(rule => rule.allowed_fields || [])
    .filter((v, i, a) => a.indexOf(v) === i); // 중복 제거

  const meta: Record<string, unknown> = {};
  if (payload && typeof payload === 'object') {
    for (const field of allowedFields) {
      if (field in payload) {
        meta[field] = payload[field];
      }
    }
  }

  return meta;
}

