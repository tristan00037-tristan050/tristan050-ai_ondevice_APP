import React, { useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import {
  connectCompanyLearningFolder,
  getCompanyLearningStatus,
  getCompanyLearningUnderstanding,
  handoffCompanyLearningCandidate,
} from '../../lib/company_learning/client';
import type {
  AdminContextForSidecar,
  CompanyLearningConnectResponse,
  CompanyLearningHandoffResponse,
  CompanyLearningStatusResponse,
  CompanyLearningUnderstanding,
} from '../../lib/company_learning/contracts';
import {
  getExistingAdminContextForA2,
  type ExistingAdminContextInput,
} from '../../lib/admin_policy/adminContext';

const FAIL_CLASS_MESSAGES: Record<string, string> = {
  ADMIN_AUTH_REQUIRED: '관리자 인증 정보가 없습니다.',
  ADMIN_CONTEXT_INVALID: '관리자 인증 형식이 올바르지 않습니다.',
  ADMIN_RBAC_DENIED: '관리자 권한이 필요합니다.',
  ADMIN_DIGEST_PLACEHOLDER: '임시 관리자 식별값은 사용할 수 없습니다.',
  ADMIN_AUTH_METHOD_NOT_ALLOWED: '테스트 인증 방식은 운영 화면에서 사용할 수 없습니다.',
  ADMIN_ROLE_REGISTRY_EMPTY: '직급 등록이 아직 초기화되지 않았습니다.',
  ADMIN_ROLE_NOT_REGISTERED: '현재 계정은 등록된 관리자가 아닙니다.',
  FOLDER_NOT_FOUND: '폴더를 찾을 수 없습니다.',
  NO_INDEXABLE_FILES: '인덱싱할 수 있는 지원 파일이 없습니다.',
  JOB_NOT_FOUND: '작업이 만료되었거나 존재하지 않습니다.',
  NEEDS_REVIEW_CONFIRMATION_REQUIRED: '근거 부족 항목은 관리자 확인 후 후보 등록할 수 있습니다.',
  HANDOFF_DLP_FAILED: 'DLP 검사에 실패해 후보 등록을 중단했습니다.',
  LEARNING_EVENT_ALREADY_EXISTS: '이미 이 작업의 학습 후보가 등록되었습니다.',
};

const DEFAULT_FORM: ExistingAdminContextInput = {
  role: 'admin',
  adminIdDigest: '',
  adminSessionDigest: '',
  authMethod: 'tauri_secure_invoke',
};

function extractFailClass(error: unknown): string {
  if (error && typeof error === 'object' && 'failClass' in error) {
    const fc = (error as { failClass?: unknown }).failClass;
    if (typeof fc === 'string' && fc.length > 0) return fc;
  }
  return 'UNKNOWN';
}

function uiErrorMessage(error: unknown): string {
  const failClass = extractFailClass(error);
  return FAIL_CLASS_MESSAGES[failClass] ?? `작업을 완료하지 못했습니다. 오류 코드: ${failClass}`;
}

function CounterRow({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ color: '#64748B' }}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function CompanyLearningConsole({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<ExistingAdminContextInput>(DEFAULT_FORM);
  const [admin, setAdmin] = useState<AdminContextForSidecar | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [connectResult, setConnectResult] = useState<CompanyLearningConnectResponse | null>(null);
  const [status, setStatus] = useState<CompanyLearningStatusResponse | null>(null);
  const [understanding, setUnderstanding] = useState<CompanyLearningUnderstanding | null>(null);
  const [handoff, setHandoff] = useState<CompanyLearningHandoffResponse | null>(null);
  const [adminConfirmedNeedsReview, setAdminConfirmedNeedsReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applyAuth(): void {
    setAuthError(null);
    try {
      setAdmin(getExistingAdminContextForA2(form));
    } catch (caught) {
      setAdmin(null);
      setAuthError(uiErrorMessage(caught));
    }
  }

  async function handleConnectFolder(): Promise<void> {
    if (!admin || busy) return;
    setBusy(true);
    setError(null);
    setHandoff(null);
    setAdminConfirmedNeedsReview(false);
    try {
      const selected = await openDialog({ directory: true, multiple: false });
      const selectedPath = typeof selected === 'string' ? selected : null;
      if (!selectedPath) return;
      setConnectResult(null);
      setStatus(null);
      setUnderstanding(null);
      const connected = await connectCompanyLearningFolder(selectedPath, admin);
      setConnectResult(connected);
      const latestStatus = await getCompanyLearningStatus(connected.job_id, admin);
      setStatus(latestStatus);
      const nextUnderstanding = await getCompanyLearningUnderstanding(connected.job_id, admin);
      setUnderstanding(nextUnderstanding);
    } catch (caught) {
      setError(uiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefresh(): Promise<void> {
    if (!admin || !connectResult || busy) return;
    setBusy(true);
    setError(null);
    try {
      setStatus(await getCompanyLearningStatus(connectResult.job_id, admin));
      setUnderstanding(await getCompanyLearningUnderstanding(connectResult.job_id, admin));
    } catch (caught) {
      setError(uiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleHandoff(): Promise<void> {
    if (!admin || !connectResult || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await handoffCompanyLearningCandidate(
        connectResult.job_id,
        adminConfirmedNeedsReview,
        admin,
      );
      setHandoff(result);
    } catch (caught) {
      setError(uiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const canHandoff = Boolean(
    admin &&
      connectResult &&
      understanding &&
      (!understanding.needs_review || adminConfirmedNeedsReview) &&
      !handoff,
  );

  return (
    <div
      data-testid="company-learning-console"
      role="dialog"
      aria-modal="true"
      aria-label="회사 폴더 학습 후보"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(15,23,42,0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div style={{ background: '#fff', borderRadius: 8, padding: 20, width: 'min(980px, 96vw)', maxHeight: '92vh', overflow: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>회사 폴더 학습 후보</h2>
          <button onClick={onClose} aria-label="닫기" style={{ marginLeft: 'auto' }}>
            닫기
          </button>
        </div>
        <p style={{ marginTop: 0, color: '#475569', fontSize: 13 }}>
          폴더 내용은 이 기기 안에서만 읽습니다. 원문/경로 저장 안 함. 학습 실행이 아니라 후보 등록.
        </p>

        <section style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12, marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>관리자 인증</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              관리자 인증값
              <input
                aria-label="Learning Admin ID digest"
                type="password"
                autoComplete="off"
                value={form.adminIdDigest}
                onChange={event => setForm(s => ({ ...s, adminIdDigest: event.target.value }))}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              로그인 확인값
              <input
                aria-label="Learning Admin session digest"
                type="password"
                autoComplete="off"
                value={form.adminSessionDigest}
                onChange={event => setForm(s => ({ ...s, adminSessionDigest: event.target.value }))}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              인증 방식
              <select
                aria-label="Learning Admin auth method"
                value={form.authMethod}
                onChange={event => setForm(s => ({ ...s, authMethod: event.target.value }))}
              >
                <option value="tauri_secure_invoke">tauri_secure_invoke</option>
                <option value="os_keychain">os_keychain</option>
              </select>
            </label>
            <div>
              <button data-testid="learning-apply-auth-btn" onClick={applyAuth}>
                인증 적용
              </button>
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 13 }} data-testid="learning-auth-status">
            {admin ? <span style={{ color: '#15803D' }}>인증 적용됨</span> : <span style={{ color: '#9A3412' }}>인증되지 않음</span>}
          </div>
          {authError && <div role="alert" style={{ marginTop: 8, color: '#B91C1C', fontSize: 13 }}>{authError}</div>}
        </section>

        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button data-testid="choose-learning-folder-btn" disabled={!admin || busy} onClick={handleConnectFolder}>
            폴더 선택
          </button>
          <button data-testid="refresh-learning-job-btn" disabled={!connectResult || busy} onClick={handleRefresh}>
            새로고침
          </button>
          {busy && <span style={{ color: '#64748B', fontSize: 13 }}>처리 중…</span>}
        </div>

        {error && <div role="alert" style={{ color: '#B91C1C', marginBottom: 12 }}>{error}</div>}

        {connectResult && (
          <section data-testid="learning-job-panel" style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12, marginBottom: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>폴더 분석</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, fontSize: 13 }}>
              <CounterRow label="지원 파일" value={connectResult.counters.processed_files} />
              <CounterRow label="분석 조각" value={connectResult.counters.chunk_count} />
              <CounterRow label="건너뛴 파일" value={connectResult.counters.skipped_unsupported} />
              <CounterRow label="읽지 못한 파일" value={connectResult.counters.skipped_extractor} />
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: '#475569' }}>
              {status ? `분석 준비 완료 · ${status.progress}%` : '폴더 연결 완료'}
            </div>
          </section>
        )}

        {understanding && (
          <section data-testid="learning-understanding-panel" style={{ border: '1px solid #BFDBFE', borderRadius: 8, padding: 12, marginBottom: 12, background: '#EFF6FF' }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>업무 파악</div>
            <div style={{ fontSize: 13, marginBottom: 8 }}>{understanding.summary_runtime_text}</div>
            <div style={{ fontSize: 12, color: '#1D4ED8', marginBottom: 8 }}>
              이 기기 안에서만 처리됨 · 근거 {understanding.evidence_chip_count}개
            </div>
            {understanding.needs_review && (
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10, fontSize: 13 }}>
                <input
                  data-testid="learning-admin-confirm-checkbox"
                  type="checkbox"
                  checked={adminConfirmedNeedsReview}
                  onChange={event => setAdminConfirmedNeedsReview(event.target.checked)}
                />
                근거 부족 항목은 확인 필요
              </label>
            )}
            <div style={{ display: 'grid', gap: 8 }}>
              {understanding.claims.map(claim => (
                <div key={claim.claim_id} style={{ background: '#fff', border: '1px solid #DBEAFE', borderRadius: 8, padding: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{claim.claim_runtime_text}</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {claim.evidence_chips.map((chip, chipIndex) => (
                      <span
                        data-testid="learning-evidence-chip"
                        key={`${claim.claim_id}-${chip.chunk_digest}`}
                        style={{ fontSize: 11, border: '1px solid #CBD5E1', borderRadius: 999, padding: '2px 8px', background: '#F8FAFC' }}
                      >
                        근거 {chipIndex + 1} · 문서 위치 {chip.char_span[0]}-{chip.char_span[1]}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 10 }}>
              <button data-testid="learning-handoff-btn" disabled={!canHandoff || busy} onClick={handleHandoff}>
                학습 후보 등록
              </button>
            </div>
          </section>
        )}

        {handoff && (
          <section data-testid="learning-handoff-result" style={{ border: '1px solid #BBF7D0', borderRadius: 8, padding: 12, background: '#F0FDF4' }}>
            <div style={{ fontWeight: 700, color: '#166534' }}>후보 등록 완료</div>
            <div style={{ fontSize: 13, color: '#166534' }}>
              후보 등록 완료 (학습 실행 아님)
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
