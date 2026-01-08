/**
 * Egress Guard v1 테스트
 * 스키마 위반 payload가 실제로 전송 0인지 확인 (모킹)
 */

import { guardEgressPayload, extractEgressAudit } from './guard';
import { ClientCfg } from '../hud/accounting-api';

const mockCfg: ClientCfg = {
  baseUrl: 'http://localhost:8081',
  tenantId: 'test-tenant',
  apiKey: 'test-key',
  mode: 'live',
};

describe('Egress Guard v1', () => {
  test('허용 payload PASS', () => {
    const payload = {
      action: 'approve',
      client_request_id: 'req-123',
      note: 'Test note',
    };
    const result = guardEgressPayload(mockCfg, payload);
    expect(result.pass).toBe(true);
    expect(result.blocked).toBe(false);
  });

  test('금지 필드 포함 시 FAIL (차단)', () => {
    const payload = {
      action: 'approve',
      raw_text: 'forbidden field',
    };
    const result = guardEgressPayload(mockCfg, payload);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBe('FORBIDDEN_FIELD_DETECTED');
  });

  test('허용되지 않은 필드 포함 시 FAIL (차단)', () => {
    const payload = {
      action: 'approve',
      unknown_field: 'not allowed',
    };
    const result = guardEgressPayload(mockCfg, payload);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBe('UNALLOWED_FIELD_DETECTED');
  });

  test('limitDays 초과 시 FAIL (차단)', () => {
    const payload = {
      limitDays: 100,
    };
    const result = guardEgressPayload(mockCfg, payload);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBe('INVALID_LIMIT_DAYS');
  });

  test('currency 형식 오류 시 FAIL (차단)', () => {
    const payload = {
      currency: 'KR',
    };
    const result = guardEgressPayload(mockCfg, payload);
    expect(result.pass).toBe(false);
    expect(result.blocked).toBe(true);
    expect(result.reason_code).toBe('INVALID_CURRENCY_FORMAT');
  });

  test('Mock 모드에서는 검증 스킵', () => {
    const mockCfgMock: ClientCfg = {
      ...mockCfg,
      mode: 'mock',
    };
    const payload = {
      raw_text: 'forbidden',
    };
    const result = guardEgressPayload(mockCfgMock, payload);
    expect(result.pass).toBe(true);
    expect(result.blocked).toBe(false);
  });

  test('감사 로그 meta-only 추출', () => {
    const result = {
      pass: false,
      blocked: true,
      reason_code: 'FORBIDDEN_FIELD_DETECTED',
      policy_version: '1.0',
    };
    const audit = extractEgressAudit(result);
    expect(audit).toEqual({
      blocked: true,
      reason_code: 'FORBIDDEN_FIELD_DETECTED',
      policy_version: '1.0',
    });
    // 본문이 포함되지 않았는지 확인
    expect(audit).not.toHaveProperty('payload');
    expect(audit).not.toHaveProperty('body');
  });
});

