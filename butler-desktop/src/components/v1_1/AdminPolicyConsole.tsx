import React, { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ShieldCheck, X } from 'lucide-react';
import { registerCompanyPolicy, type AdminPolicyClientError } from '../../lib/admin_policy/client';
import {
  DEFAULT_EXTERNAL_SEND_RULES,
  DOC_GRADES,
  POLICY_DECISIONS,
  type AccessRulePayload,
  type AdminAuthMethod,
  type AdminHeaders,
  type AdminRole,
  type CompanyPolicyRegisterResponse,
  type Sha256Digest,
  buildAdminHeadersInput,
  isSha256Digest,
  validateCompanyPolicyRegisterRequest,
} from '../../lib/admin_policy/contracts';
import {
  DOC_GRADE_DISPLAY,
  POLICY_DECISION_DISPLAY,
  ROLE_LABELS,
  STATUS_LABELS,
} from '../../lib/admin_display/copy';

// EMPTY_DIGEST 는 비어있는 form 초기값 — Sha256Digest template literal 의무 정합으로
// padEnd 결과를 명시적으로 단언 (tsc strict 통과). 실 등록 직전 isSha256Digest 가드로
// 정확 형식만 통과 (런타임 안전성 유지).
const EMPTY_DIGEST = 'sha256:'.padEnd(71, '0') as Sha256Digest;

type ConsoleState = {
  adminRole: AdminRole;
  adminIdDigest: string;
  adminSessionDigest: string;
  authMethod: AdminAuthMethod;
  version: number;
  status: 'ACTIVE' | 'DRAFT' | 'DEPRECATED';
  maskingEngineVerified: boolean;
  rule: AccessRulePayload;
};

const initialState: ConsoleState = {
  adminRole: 'admin',
  adminIdDigest: EMPTY_DIGEST,
  adminSessionDigest: EMPTY_DIGEST,
  authMethod: 'tauri_secure_invoke',
  version: 1,
  status: 'ACTIVE',
  maskingEngineVerified: false,
  rule: {
    dept_digest: EMPTY_DIGEST,
    role: 'employee',
    doc_grade: 'internal',
    decision: 'allow',
    reason_code: 'RULE_MATCHED',
  },
};

function toAdminHeaders(state: ConsoleState): AdminHeaders {
  return buildAdminHeadersInput({
    role: state.adminRole,
    adminIdDigest: state.adminIdDigest,
    adminSessionDigest: state.adminSessionDigest,
    authMethod: state.authMethod,
  });
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" style={{ border: '1px solid #F59E0B', background: '#FFFBEB', color: '#7C2D12', borderRadius: 8, padding: 12, display: 'flex', gap: 8 }}>
      <AlertTriangle size={18} aria-hidden />
      <span>{message}</span>
    </div>
  );
}

function SuccessBox() {
  return (
    <div data-testid="admin-policy-success" style={{ border: '1px solid #86EFAC', background: '#F0FDF4', color: '#14532D', borderRadius: 8, padding: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
        <CheckCircle2 size={18} aria-hidden />
        회사 보안 규칙 등록 완료
      </div>
      <p style={{ margin: '8px 0 0', fontSize: 13 }}>보안 기록이 안전하게 남았습니다. 원문은 저장하지 않습니다.</p>
    </div>
  );
}

export function AdminPolicyConsole({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<ConsoleState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<CompanyPolicyRegisterResponse | null>(null);

  const request = useMemo(
    () => ({
      version: state.version,
      status: state.status,
      masking_engine_verified: state.maskingEngineVerified,
      access_rules: [state.rule],
    }),
    [state],
  );
  const validationErrors = useMemo(() => validateCompanyPolicyRegisterRequest(request), [request]);
  const adminDigestReady = isSha256Digest(state.adminIdDigest) && isSha256Digest(state.adminSessionDigest);
  const canSubmit = validationErrors.length === 0 && adminDigestReady && !submitting;

  async function submitPolicy(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    if (!canSubmit) {
      setError('정책 입력값을 확인해 주세요.');
      return;
    }
    if (state.adminRole !== 'admin') {
      setError('관리자 권한이 필요합니다.');
      return;
    }
    setSubmitting(true);
    try {
      const admin = toAdminHeaders(state);
      const result = await registerCompanyPolicy(request, admin);
      setResponse(result);
    } catch (caught) {
      const err = caught as AdminPolicyClientError;
      if (err.status === 401 || err.status === 403 || err.failClass?.startsWith('ADMIN_')) {
        setError('관리자 권한이 필요합니다.');
      } else {
        setError(err.message || '정책 등록에 실패했습니다.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div data-testid="admin-policy-console" role="dialog" aria-modal="true" aria-label="관리자 정책 등록" style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <section style={{ width: 'min(980px, 100%)', maxHeight: '92vh', overflow: 'auto', background: '#FFFFFF', borderRadius: 12, padding: 24, boxShadow: '0 24px 80px rgba(15,23,42,0.24)' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <ShieldCheck size={24} aria-hidden />
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 20 }}>관리자 정책 등록</h2>
            <p style={{ margin: '4px 0 0', color: '#64748B', fontSize: 13 }}>회사 보안 규칙을 등록하는 화면입니다. 원문은 저장하지 않습니다.</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 8, padding: 6 }}>
            <X size={18} aria-hidden />
          </button>
        </header>

        <form onSubmit={submitPolicy} style={{ display: 'grid', gap: 18 }}>
          <fieldset style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <legend style={{ padding: '0 6px', fontWeight: 700 }}>관리자 확인</legend>
            <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 1fr', gap: 12 }}>
              <label>
                역할
                <select aria-label="관리자 역할" value={state.adminRole} onChange={event => setState(s => ({ ...s, adminRole: event.target.value as AdminRole }))}>
                  <option value="admin">{ROLE_LABELS.admin}</option>
                  <option value="manager">{ROLE_LABELS.manager}</option>
                  <option value="employee">{ROLE_LABELS.employee}</option>
                </select>
              </label>
              <label>
                관리자 인증값
                <input aria-label="Admin ID digest" type="password" autoComplete="off" value={state.adminIdDigest} onChange={event => setState(s => ({ ...s, adminIdDigest: event.target.value }))} />
              </label>
              <label>
                로그인 확인값
                <input aria-label="Admin session digest" type="password" autoComplete="off" value={state.adminSessionDigest} onChange={event => setState(s => ({ ...s, adminSessionDigest: event.target.value }))} />
              </label>
              <label>
                인증 방식
                <select aria-label="Admin auth method" value={state.authMethod} onChange={event => setState(s => ({ ...s, authMethod: event.target.value as AdminAuthMethod }))}>
                  <option value="tauri_secure_invoke">보안 인증</option>
                  <option value="os_keychain">기기 암호 보관함</option>
                </select>
              </label>
              <p style={{ gridColumn: 'span 2', margin: 0, color: '#64748B', fontSize: 12 }}>관리자 인증값만 사용합니다. 로그인 토큰을 관리자 권한으로 쓰지 않습니다.</p>
            </div>
          </fieldset>

          <fieldset style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <legend style={{ padding: '0 6px', fontWeight: 700 }}>정책 본문</legend>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 180px 1fr', gap: 12, marginBottom: 14 }}>
              <label>
                규칙 버전
                <input aria-label="정책 version" type="number" min={1} value={state.version} onChange={event => setState(s => ({ ...s, version: Number(event.target.value) }))} />
              </label>
              <label>
                상태
                <select aria-label="정책 status" value={state.status} onChange={event => setState(s => ({ ...s, status: event.target.value as ConsoleState['status'] }))}>
                  <option value="ACTIVE">{STATUS_LABELS.ACTIVE}</option>
                  <option value="DRAFT">{STATUS_LABELS.DRAFT}</option>
                  <option value="DEPRECATED">{STATUS_LABELS.DEPRECATED}</option>
                </select>
              </label>
              <label style={{ alignSelf: 'end' }}>
                <input type="checkbox" checked={state.maskingEngineVerified} onChange={event => setState(s => ({ ...s, maskingEngineVerified: event.target.checked }))} /> 민감정보 가림 확인
              </label>
            </div>
            {!state.maskingEngineVerified && <p data-testid="masking-blocked-note" style={{ color: '#92400E', background: '#FFFBEB', padding: 10, borderRadius: 8, margin: '0 0 14px' }}>민감정보 가림 확인 전입니다. 확인되기 전에는 외부 전송을 막고 검토 필요로 처리합니다.</p>}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 140px 160px 160px 160px', gap: 10 }}>
              <label>
                부서
                <input aria-label="부서 digest" type="password" autoComplete="off" value={state.rule.dept_digest} onChange={event => setState(s => ({ ...s, rule: { ...s.rule, dept_digest: event.target.value as AccessRulePayload['dept_digest'] } }))} />
              </label>
              <label>
                역할
                <select aria-label="규칙 role" value={state.rule.role} onChange={event => setState(s => ({ ...s, rule: { ...s.rule, role: event.target.value as AccessRulePayload['role'] } }))}>
                  <option value="employee">{ROLE_LABELS.employee}</option>
                  <option value="manager">{ROLE_LABELS.manager}</option>
                  <option value="admin">{ROLE_LABELS.admin}</option>
                </select>
              </label>
              <label>
                공개 등급
                <select aria-label="문서 등급" value={state.rule.doc_grade} onChange={event => setState(s => ({ ...s, rule: { ...s.rule, doc_grade: event.target.value as AccessRulePayload['doc_grade'] } }))}>
                  {DOC_GRADES.map(grade => <option key={grade} value={grade}>{DOC_GRADE_DISPLAY[grade]}</option>)}
                </select>
              </label>
              <label>
                처리 방법
                <select aria-label="정책 decision" value={state.rule.decision} onChange={event => setState(s => ({ ...s, rule: { ...s.rule, decision: event.target.value as AccessRulePayload['decision'] } }))}>
                  {POLICY_DECISIONS.map(decision => <option key={decision} value={decision}>{POLICY_DECISION_DISPLAY[decision]}</option>)}
                </select>
              </label>
              <label>
                사유
                <input aria-label="reason code" value={state.rule.reason_code} onChange={event => setState(s => ({ ...s, rule: { ...s.rule, reason_code: event.target.value } }))} />
              </label>
            </div>
          </fieldset>

          <section aria-label="외부 전송 기본 정책" style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <h3 style={{ margin: '0 0 10px', fontSize: 15 }}>외부 전송 규칙</h3>
            <p style={{ margin: '0 0 12px', color: '#64748B', fontSize: 13 }}>외부 전송 기준은 현재 기본값으로 적용됩니다.</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
              {DOC_GRADES.map(grade => (
                <label key={grade} style={{ display: 'grid', gap: 4 }}>
                  {DOC_GRADE_DISPLAY[grade]}
                  <input readOnly aria-label={`${grade} external send`} value={POLICY_DECISION_DISPLAY[DEFAULT_EXTERNAL_SEND_RULES[grade]]} />
                </label>
              ))}
            </div>
          </section>

          {validationErrors.length > 0 && <ErrorBox message={`입력 검증: ${validationErrors.join(', ')}`} />}
          {error && <ErrorBox message={error} />}
          {response && <SuccessBox />}

          <button type="submit" disabled={!canSubmit} style={{ padding: 14, borderRadius: 10, border: 0, background: canSubmit ? '#0F766E' : '#CBD5E1', color: '#FFFFFF', fontWeight: 700 }}>
            {submitting ? '등록 중' : '정책 등록'}
          </button>
        </form>
      </section>
    </div>
  );
}
