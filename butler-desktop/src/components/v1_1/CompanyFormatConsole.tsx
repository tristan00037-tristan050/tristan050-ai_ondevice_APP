import React, { useMemo, useState } from 'react';
import { CheckCircle2, FileText, ShieldCheck, X } from 'lucide-react';
import { registerCompanyFormat, type AdminPolicyClientError } from '../../lib/admin_policy/client';
import {
  FORMAT_KIND_LABELS,
  FORMAT_KINDS,
  type AdminAuthMethod,
  type AdminRole,
  type CompanyFormatRegisterResponse,
  type FormatKind,
  type Sha256Digest,
  buildAdminHeadersInput,
  isSha256Digest,
  validateCompanyFormatRegisterRequest,
} from '../../lib/admin_policy/contracts';

const EMPTY_DIGEST = 'sha256:'.padEnd(71, '0') as Sha256Digest;

type FormatConsoleState = {
  adminRole: AdminRole;
  adminIdDigest: string;
  adminSessionDigest: string;
  authMethod: AdminAuthMethod;
  templateRuntimeText: string;
  titleRuntimeText: string;
  formatKind: FormatKind;
  language: string;
  deptDigest: string;
};

const initialState: FormatConsoleState = {
  adminRole: 'admin',
  adminIdDigest: EMPTY_DIGEST,
  adminSessionDigest: EMPTY_DIGEST,
  authMethod: 'tauri_secure_invoke',
  templateRuntimeText: '',
  titleRuntimeText: '',
  formatKind: 'report',
  language: 'ko',
  deptDigest: EMPTY_DIGEST,
};

function ResultPanel({ response }: { response: CompanyFormatRegisterResponse }) {
  return (
    <div data-testid="company-format-success" style={{ border: '1px solid #86EFAC', background: '#F0FDF4', color: '#14532D', borderRadius: 8, padding: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
        <CheckCircle2 size={18} aria-hidden />
        회사 양식 등록 완료
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: '140px minmax(0, 1fr)', gap: 6, margin: '10px 0 0', fontSize: 12 }}>
        <dt>format_id</dt>
        <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{response.format_id}</dd>
        <dt>format_digest</dt>
        <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{response.format_digest}</dd>
        <dt>template_digest</dt>
        <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{response.template_digest}</dd>
        <dt>template_ref</dt>
        <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{response.template_ref}</dd>
        <dt>encrypted_store</dt>
        <dd style={{ margin: 0 }}>{String(response.encrypted_store)}</dd>
      </dl>
    </div>
  );
}

export function CompanyFormatConsole({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<FormatConsoleState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<CompanyFormatRegisterResponse | null>(null);

  const request = useMemo(
    () => ({
      template_runtime_text: state.templateRuntimeText,
      format_kind: state.formatKind,
      title_runtime_text: state.titleRuntimeText,
      language: state.language,
      // form input string 을 Sha256Digest 로 단언 — validateCompanyFormatRegisterRequest
      // 가 isSha256Digest 가드로 실제 형식 검증을 수행하므로 type assertion 안전.
      dept_digest: state.deptDigest as Sha256Digest,
    }),
    [state],
  );
  const validationErrors = useMemo(() => validateCompanyFormatRegisterRequest(request), [request]);
  const adminReady = isSha256Digest(state.adminIdDigest) && isSha256Digest(state.adminSessionDigest) && state.adminRole === 'admin';
  const canSubmit = validationErrors.length === 0 && adminReady && !submitting;

  async function submitFormat(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    if (!canSubmit) {
      setError(state.adminRole !== 'admin' ? '관리자 권한이 필요합니다.' : '양식 입력값을 확인해 주세요.');
      return;
    }
    setSubmitting(true);
    try {
      const admin = buildAdminHeadersInput({
        role: state.adminRole,
        adminIdDigest: state.adminIdDigest,
        adminSessionDigest: state.adminSessionDigest,
        authMethod: state.authMethod,
      });
      const result = await registerCompanyFormat(request, admin);
      setResponse(result);
      setState(s => ({
        ...s,
        templateRuntimeText: '',
        titleRuntimeText: '',
      }));
    } catch (caught) {
      const err = caught as AdminPolicyClientError;
      setError(err.status === 403 || err.failClass?.startsWith('ADMIN_') ? '관리자 권한이 필요합니다.' : err.message || '양식 등록에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div data-testid="company-format-console" role="dialog" aria-modal="true" aria-label="회사 양식 등록" style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <section style={{ width: 'min(980px, 100%)', maxHeight: '92vh', overflow: 'auto', background: '#FFFFFF', borderRadius: 12, padding: 24, boxShadow: '0 24px 80px rgba(15,23,42,0.24)' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <FileText size={24} aria-hidden />
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 20 }}>회사 양식 등록</h2>
            <p style={{ margin: '4px 0 0', color: '#64748B', fontSize: 13 }}>양식 원문은 화면 메모리에만 두고, backend가 device-local encrypted vault에 저장합니다.</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 8, padding: 6 }}>
            <X size={18} aria-hidden />
          </button>
        </header>

        <form onSubmit={submitFormat} style={{ display: 'grid', gap: 18 }}>
          <fieldset style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <legend style={{ padding: '0 6px', fontWeight: 700 }}>Admin RBAC</legend>
            <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 1fr', gap: 12 }}>
              <label>
                역할
                <select aria-label="관리자 역할" value={state.adminRole} onChange={event => setState(s => ({ ...s, adminRole: event.target.value as AdminRole }))}>
                  <option value="admin">admin</option>
                  <option value="manager">manager</option>
                  <option value="employee">employee</option>
                </select>
              </label>
              <label>
                Admin ID digest
                <input aria-label="Admin ID digest" value={state.adminIdDigest} onChange={event => setState(s => ({ ...s, adminIdDigest: event.target.value }))} />
              </label>
              <label>
                Admin session digest
                <input aria-label="Admin session digest" value={state.adminSessionDigest} onChange={event => setState(s => ({ ...s, adminSessionDigest: event.target.value }))} />
              </label>
              <label>
                Auth method
                <select aria-label="Admin auth method" value={state.authMethod} onChange={event => setState(s => ({ ...s, authMethod: event.target.value as AdminAuthMethod }))}>
                  <option value="tauri_secure_invoke">tauri_secure_invoke</option>
                  <option value="os_keychain">os_keychain</option>
                  <option value="test_only">test_only</option>
                </select>
              </label>
              <p style={{ gridColumn: 'span 2', margin: 0, color: '#64748B', fontSize: 12 }}>token을 admin 권한으로 간주하지 않습니다. 관리자 digest header만 사용합니다.</p>
            </div>
          </fieldset>

          <fieldset style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <legend style={{ padding: '0 6px', fontWeight: 700 }}>양식 본문</legend>
            <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 1fr', gap: 12, marginBottom: 12 }}>
              <label>
                format_kind
                <select aria-label="양식 종류" value={state.formatKind} onChange={event => setState(s => ({ ...s, formatKind: event.target.value as FormatKind }))}>
                  {FORMAT_KINDS.map(kind => <option key={kind} value={kind}>{FORMAT_KIND_LABELS[kind]} ({kind})</option>)}
                </select>
              </label>
              <label>
                title_runtime_text
                <input aria-label="양식 제목" value={state.titleRuntimeText} onChange={event => setState(s => ({ ...s, titleRuntimeText: event.target.value }))} />
              </label>
              <label>
                dept_digest
                <input aria-label="부서 digest" value={state.deptDigest} onChange={event => setState(s => ({ ...s, deptDigest: event.target.value }))} />
              </label>
              <label>
                language
                <input aria-label="language" value={state.language} onChange={event => setState(s => ({ ...s, language: event.target.value }))} />
              </label>
            </div>
            <label style={{ display: 'grid', gap: 6 }}>
              template_runtime_text
              <textarea
                aria-label="양식 원문"
                value={state.templateRuntimeText}
                onChange={event => setState(s => ({ ...s, templateRuntimeText: event.target.value }))}
                rows={10}
                placeholder="회사 양식 원문을 붙여넣으세요. 제출 후 화면 state에서 즉시 제거됩니다."
              />
            </label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, color: '#0F766E', fontSize: 13 }}>
              <ShieldCheck size={16} aria-hidden />
              브라우저 저장소 사용 0 · raw log 0 · 127.0.0.1 sidecar only
            </div>
          </fieldset>

          <section style={{ border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>v1.2 한계</h3>
            <p style={{ margin: 0, color: '#64748B', fontSize: 13 }}>목록·롤백 endpoint는 #772에 없습니다. 이번 UI는 등록과 adapter digest preview 준비까지만 claim합니다. 박스 2 연동은 별도 검증 전까지 미지원입니다.</p>
          </section>

          {validationErrors.length > 0 && <div role="alert" style={{ color: '#7C2D12', background: '#FFFBEB', padding: 12, borderRadius: 8 }}>입력 검증: {validationErrors.join(', ')}</div>}
          {error && <div role="alert" style={{ color: '#7C2D12', background: '#FFFBEB', padding: 12, borderRadius: 8 }}>{error}</div>}
          {response && <ResultPanel response={response} />}

          <button type="submit" disabled={!canSubmit} style={{ padding: 14, borderRadius: 10, border: 0, background: canSubmit ? '#0F766E' : '#CBD5E1', color: '#FFFFFF', fontWeight: 700 }}>
            {submitting ? '등록 중' : '양식 등록'}
          </button>
        </form>
      </section>
    </div>
  );
}
