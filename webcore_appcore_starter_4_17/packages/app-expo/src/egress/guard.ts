/**
 * Egress Guard v1 (Meta-Only Whitelist)
 * Live 모드에서 서버로 나가는 모든 payload를 화이트리스트 스키마로 검증
 * 실패 시 네트워크 요청 자체를 차단 (Fail-Closed)
 */

import { isMock, type ClientCfg } from '../hud/accounting-api';

export interface EgressGuardResult {
  pass: boolean;
  blocked?: boolean;
  reason_code?: string;
  policy_version?: string;
}

const POLICY_VERSION = '1.0';

// 간단한 스키마 검증 (JSON Schema 라이브러리 없이)
function validateEgressPayload(payload: any): EgressGuardResult {
  if (!payload || typeof payload !== 'object') {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_PAYLOAD_TYPE',
      policy_version: POLICY_VERSION,
    };
  }

  // 금지 필드 검사 (원문/문장 조각 포함 금지)
  const forbiddenFields = [
    'raw_text',
    'full_content',
    'original_message',
    'token',
    'secret',
    'password',
    'api_key',
    'body',
    'payload',
  ];

  for (const field of forbiddenFields) {
    if (field in payload) {
      return {
        pass: false,
        blocked: true,
        reason_code: 'FORBIDDEN_FIELD_DETECTED',
        policy_version: POLICY_VERSION,
      };
    }
  }

  // 허용 필드 검사 (화이트리스트)
  const allowedFields = [
    'action',
    'client_request_id',
    'note',
    'top1_selected',
    'selected_rank',
    'ai_score',
    'since',
    'until',
    'limitDays',
    'severity',
    'bank_id',
    'ledger_id',
    'sessionId',
    'description',
    'amount',
    'currency',
    'subject_type',
    'subject_id',
    'reason',
    'reason_code',
    'is_high_value',
  ];

  for (const key in payload) {
    if (!allowedFields.includes(key)) {
      return {
        pass: false,
        blocked: true,
        reason_code: 'UNALLOWED_FIELD_DETECTED',
        policy_version: POLICY_VERSION,
      };
    }
  }

  // 타입 검증
  if (payload.action && typeof payload.action !== 'string') {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_ACTION_TYPE',
      policy_version: POLICY_VERSION,
    };
  }

  if (payload.note && (typeof payload.note !== 'string' || payload.note.length > 500)) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_NOTE_FORMAT',
      policy_version: POLICY_VERSION,
    };
  }

  if (payload.limitDays && (typeof payload.limitDays !== 'number' || payload.limitDays < 1 || payload.limitDays > 90)) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_LIMIT_DAYS',
      policy_version: POLICY_VERSION,
    };
  }

  if (payload.amount !== undefined && (typeof payload.amount !== 'number' || payload.amount < 0)) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_AMOUNT',
      policy_version: POLICY_VERSION,
    };
  }

  if (payload.currency && (typeof payload.currency !== 'string' || !/^[A-Z]{3}$/.test(payload.currency))) {
    return {
      pass: false,
      blocked: true,
      reason_code: 'INVALID_CURRENCY_FORMAT',
      policy_version: POLICY_VERSION,
    };
  }

  return {
    pass: true,
    blocked: false,
    policy_version: POLICY_VERSION,
  };
}

/**
 * Egress Guard: Live 모드에서만 payload 검증
 */
export function guardEgressPayload(cfg: ClientCfg, payload: any): EgressGuardResult {
  // Mock 모드에서는 검증 스킵
  if (isMock(cfg)) {
    return {
      pass: true,
      blocked: false,
      policy_version: POLICY_VERSION,
    };
  }

  // Live 모드에서만 검증
  return validateEgressPayload(payload);
}

/**
 * 감사 로그용 meta-only 정보 추출
 */
export function extractEgressAudit(result: EgressGuardResult): Record<string, unknown> {
  return {
    blocked: result.blocked ?? false,
    reason_code: result.reason_code,
    policy_version: result.policy_version,
  };
}

