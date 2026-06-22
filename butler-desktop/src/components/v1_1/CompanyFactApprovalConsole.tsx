import React, { useState } from 'react';
import {
  approveCompanyFactCandidate,
  deprecateCompanyFact,
  getCompanyFactCandidate,
  getCompanyFactsStatus,
  listCompanyFactCandidates,
  overrideKnownBadCandidate,
  supersedeCompanyFact,
} from '../../lib/company_fact/client';
import type {
  AdminContextForSidecar,
  CompanyFactCandidateDetail,
  CompanyFactCandidateIndexEntry,
  CompanyFactSupersedeRequest,
  CompanyFactsStatusResponse,
  DeprecateReasonCode,
} from '../../lib/company_fact/contracts';
import {
  getExistingAdminContextForA2,
  type ExistingAdminContextInput,
} from '../../lib/admin_policy/adminContext';
import {
  DEPRECATE_REASON_DISPLAY,
  DEPRECATE_REASON_HELP,
  statusLabel,
} from '../../lib/admin_display/copy';

/**
 * A-2 회사 지식 후보 승인 콘솔.
 * 흐름: 인증 -> 목록 -> 상세 -> 승인/폐기 확인 모달 -> POST -> status/목록/상세 재조회.
 * raw-0: 후보 원문은 화면(React state)에서만 표시. 로그/영속저장소/외부전송/자동복사 경로 사용 0.
 */

const FAIL_CLASS_MESSAGES: Record<string, string> = {
  ADMIN_AUTH_REQUIRED: '관리자 인증 정보가 없습니다. 관리자 계정으로 다시 인증해 주세요.',
  ADMIN_CONTEXT_INVALID: '관리자 인증 형식이 올바르지 않습니다.',
  ADMIN_RBAC_DENIED: '관리자 권한이 필요합니다.',
  ADMIN_DIGEST_PLACEHOLDER: '임시 관리자 식별값은 사용할 수 없습니다. 실제 관리자 인증이 필요합니다.',
  ADMIN_AUTH_METHOD_NOT_ALLOWED: '테스트 인증 방식은 운영 화면에서 사용할 수 없습니다.',
  ADMIN_ROLE_REGISTRY_EMPTY: '직급 등록이 아직 초기화되지 않았습니다. 먼저 관리자 온보딩을 완료해 주세요.',
  ADMIN_ROLE_NOT_REGISTERED: '현재 계정은 등록된 팀장/관리자가 아닙니다.',
  ADMIN_ROLE_MISMATCH: '등록된 직급이 승인 권한과 일치하지 않습니다.',
  ADMIN_ROLE_REGISTRY_LOAD_FAILED: '직급 등록 정보를 불러오지 못했습니다. 보안상 승인을 중단했습니다.',
  COMPANY_FACT_LOAD_FAILED: '회사 지식 저장소를 불러오지 못했습니다.',
  COMPANY_FACT_CANDIDATE_NOT_FOUND: '후보를 찾을 수 없습니다. 목록을 새로고침해 주세요.',
  KNOWN_BAD_APPROVAL_BLOCKED: '재검토가 필요한 후보입니다. 관리자가 확인한 뒤 다시 승인할 수 있습니다.',
  KNOWN_BAD_OVERRIDE_MATCH_NOT_FOUND: '확인 대상 경고를 찾을 수 없습니다. 상세를 새로고침해 주세요.',
  SUPERSEDE_REQUIRES_ACTIVE: 'ACTIVE 회사 지식만 교체할 수 있습니다.',
};

/** error에서 fail_class만 안전하게 추출(allowlist). raw 메시지/원문은 렌더링하지 않는다. */
function extractFailClass(error: unknown): string {
  if (error && typeof error === 'object' && 'failClass' in error) {
    const fc = (error as { failClass?: unknown }).failClass;
    if (typeof fc === 'string' && fc.length > 0) return fc;
  }
  return 'UNKNOWN';
}

/** fail_class -> 사람이 읽는 안전 메시지. 미정의 코드는 fail_class 코드만 노출(raw 값 없음). */
function mapFailClassToMessage(failClass: string): string {
  return FAIL_CLASS_MESSAGES[failClass] ?? `작업을 완료하지 못했습니다. 오류 코드: ${failClass}`;
}

function uiErrorMessage(error: unknown): string {
  return mapFailClassToMessage(extractFailClass(error));
}

const DEFAULT_FORM: ExistingAdminContextInput = {
  role: 'admin',
  adminIdDigest: '',
  adminSessionDigest: '',
  authMethod: 'tauri_secure_invoke',
};

type ConfirmTarget = { kind: 'approve' | 'deprecate'; factId: string };

const CONFIRM_TEXT = {
  approve: '이 후보를 회사 공식 지식으로 승인하시겠습니까? 승인 후 답변에 사용될 수 있습니다.',
  deprecate: '이 회사 지식을 폐기하시겠습니까? 기록은 남지만 공식 답변에는 사용되지 않습니다.',
} as const;

const KNOWN_BAD_WARNING_TEXT =
  '재검토 필요: 이전에 틀린 정보로 표시된 항목과 핵심어/패턴이 비슷합니다.';

type SupersedeFormState = {
  category: string;
  questionPatterns: string;
  keywordsRequired: string;
  keywordsAny: string;
  answerRuntimeText: string;
  source: string;
  sourceUrl: string;
  sourceDoc: string;
  verifiedAt: string;
  expiresAt: string;
};

function fieldText(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return String(value);
}

function listText(values?: string[] | null): string {
  return values && values.length > 0 ? values.join(', ') : '—';
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map(item => item.trim())
    .filter(Boolean);
}

function splitCommaOrLines(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function buildSupersedeForm(detail: CompanyFactCandidateDetail): SupersedeFormState {
  return {
    category: detail.category ?? '',
    questionPatterns: (detail.question_patterns ?? []).join('\n'),
    keywordsRequired: (detail.keywords_required ?? []).join(', '),
    keywordsAny: (detail.keywords_any ?? []).join(', '),
    answerRuntimeText: detail.answer_runtime_text,
    source: detail.source ?? '',
    sourceUrl: detail.source_url ?? '',
    sourceDoc: detail.source_doc ?? '',
    verifiedAt: detail.verified_at ?? '',
    expiresAt: detail.expires_at ?? '',
  };
}

function toSupersedePayload(form: SupersedeFormState): CompanyFactSupersedeRequest {
  return {
    category: form.category.trim(),
    question_patterns: splitLines(form.questionPatterns),
    keywords_required: splitCommaOrLines(form.keywordsRequired),
    keywords_any: splitCommaOrLines(form.keywordsAny),
    answer_runtime_text: form.answerRuntimeText.trim(),
    source: form.source.trim(),
    source_url: form.sourceUrl.trim() || null,
    source_doc: form.sourceDoc.trim() || null,
    verified_at: form.verifiedAt.trim() || null,
    expires_at: form.expiresAt.trim() || null,
    confidence: 1.0,
  };
}

function validateSupersedePayload(payload: CompanyFactSupersedeRequest): string | null {
  if (!payload.category) return '분류를 입력해 주세요.';
  if (payload.question_patterns.length < 2) return '예상 질문을 2개 이상 입력해 주세요.';
  if (payload.answer_runtime_text.length < 10) return '답변 내용을 10자 이상 입력해 주세요.';
  if (payload.source.length < 3) return '출처를 3자 이상 입력해 주세요.';
  return null;
}

export function CompanyFactApprovalConsole({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<ExistingAdminContextInput>(DEFAULT_FORM);
  const [admin, setAdmin] = useState<AdminContextForSidecar | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<CompanyFactCandidateIndexEntry[] | null>(null);
  const [status, setStatus] = useState<CompanyFactsStatusResponse | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);

  const [detail, setDetail] = useState<CompanyFactCandidateDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);
  const [deprecateReason, setDeprecateReason] = useState<DeprecateReasonCode>('MANUAL_DEPRECATED');
  const [knownBadBlockedFactId, setKnownBadBlockedFactId] = useState<string | null>(null);
  const [inFlightFactId, setInFlightFactId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [sessionActiveFact, setSessionActiveFact] = useState<CompanyFactCandidateDetail | null>(null);
  const [supersedeTarget, setSupersedeTarget] = useState<CompanyFactCandidateDetail | null>(null);
  const [supersedeForm, setSupersedeForm] = useState<SupersedeFormState | null>(null);
  const [supersedeError, setSupersedeError] = useState<string | null>(null);

  async function refreshListAndStatus(ctx: AdminContextForSidecar): Promise<void> {
    setListLoading(true);
    setListError(null);
    try {
      const [list, st] = await Promise.all([listCompanyFactCandidates(ctx), getCompanyFactsStatus()]);
      setCandidates(list.candidates);
      setStatus(st);
    } catch (error) {
      setListError(uiErrorMessage(error));
    } finally {
      setListLoading(false);
    }
  }

  async function handleApplyAuth(): Promise<void> {
    setAuthError(null);
    let ctx: AdminContextForSidecar;
    try {
      ctx = getExistingAdminContextForA2(form);
    } catch (error) {
      setAdmin(null);
      setAuthError(uiErrorMessage(error));
      return;
    }
    setAdmin(ctx);
    setDetail(null);
    setDetailError(null);
    setSessionActiveFact(null);
    setSupersedeTarget(null);
    setSupersedeForm(null);
    await refreshListAndStatus(ctx);
  }

  async function handleSelectCandidate(factId: string): Promise<void> {
    if (!admin) return;
    setDetailLoading(true);
    setDetailError(null);
    setActionError(null);
    try {
      const next = await getCompanyFactCandidate(factId, admin);
      setDetail(next);
      setKnownBadBlockedFactId(null);
    } catch (error) {
      setDetail(null);
      setDetailError(uiErrorMessage(error));
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleConfirm(): Promise<void> {
    if (!admin || !confirmTarget) return;
    const { kind, factId } = confirmTarget;
    // 중복 실행 방지: 같은 fact_id에 대한 POST가 진행 중이면 무시.
    if (inFlightFactId === factId) return;
    setInFlightFactId(factId);
    setActionError(null);
    try {
      if (kind === 'approve') {
        const approvedSource = detail?.fact_id === factId ? detail : null;
        await approveCompanyFactCandidate(factId, admin);
        if (approvedSource) {
          setSessionActiveFact({ ...approvedSource, status: 'ACTIVE' });
        }
        setKnownBadBlockedFactId(null);
      } else {
        await deprecateCompanyFact(factId, deprecateReason, admin);
        if (sessionActiveFact?.fact_id === factId) {
          setSessionActiveFact(null);
        }
      }
      setConfirmTarget(null);
      // 성공 후에는 후보 상태가 더 이상 후보가 아니므로 상세를 다시 조회하지 않는다.
      // 목록/status만 재조회하고, 로컬 상세 영역은 비워 "성공 후 404처럼 보이는" UX를 막는다.
      setDetail(null);
      setDetailError(null);
      await refreshListAndStatus(admin);
    } catch (error) {
      const failClass = extractFailClass(error);
      if (kind === 'approve' && failClass === 'KNOWN_BAD_APPROVAL_BLOCKED') {
        setKnownBadBlockedFactId(factId);
        setActionError(mapFailClassToMessage(failClass));
      } else {
        setConfirmTarget(null);
        setActionError(uiErrorMessage(error));
      }
    } finally {
      setInFlightFactId(null);
    }
  }

  async function handleOverrideAndApprove(factId: string): Promise<void> {
    if (!admin) return;
    if (inFlightFactId === factId) return;
    setInFlightFactId(factId);
    setActionError(null);
    let overrideRecorded = false;
    try {
      await overrideKnownBadCandidate(factId, admin);
      overrideRecorded = true;
      const refreshed = await getCompanyFactCandidate(factId, admin);
      setDetail(refreshed);
      if (!refreshed.known_bad?.override_active) {
        throw new Error('KNOWN_BAD_OVERRIDE_NOT_ACTIVE');
      }
      await approveCompanyFactCandidate(factId, admin);
      setSessionActiveFact({ ...refreshed, status: 'ACTIVE' });
      setKnownBadBlockedFactId(null);
      setConfirmTarget(null);
      setDetail(null);
      setDetailError(null);
      await refreshListAndStatus(admin);
    } catch (error) {
      setActionError(
        !overrideRecorded
          ? uiErrorMessage(error)
          : error instanceof Error && error.message === 'KNOWN_BAD_OVERRIDE_NOT_ACTIVE'
          ? '관리자 확인 상태를 확인하지 못했습니다. 상세를 새로고침해 주세요.'
          : '관리자 확인은 기록되었으나 승인에 실패했습니다. 후보가 바뀌었거나 권한 문제일 수 있습니다.',
      );
      try {
        const refreshed = await getCompanyFactCandidate(factId, admin);
        setDetail(refreshed);
      } catch {
        setDetail(null);
      }
      await refreshListAndStatus(admin);
    } finally {
      setInFlightFactId(null);
    }
  }

  function openSupersedeModal(activeFact: CompanyFactCandidateDetail): void {
    setSupersedeTarget(activeFact);
    setSupersedeForm(buildSupersedeForm(activeFact));
    setSupersedeError(null);
  }

  async function handleSupersedeSubmit(): Promise<void> {
    if (!admin || !supersedeTarget || !supersedeForm) return;
    const payload = toSupersedePayload(supersedeForm);
    const validationError = validateSupersedePayload(payload);
    if (validationError) {
      setSupersedeError(validationError);
      return;
    }
    setInFlightFactId(supersedeTarget.fact_id);
    setSupersedeError(null);
    try {
      await supersedeCompanyFact(supersedeTarget.fact_id, payload, admin);
      setSessionActiveFact(null);
      setSupersedeTarget(null);
      setSupersedeForm(null);
      await refreshListAndStatus(admin);
    } catch (error) {
      setSupersedeError(uiErrorMessage(error));
    } finally {
      setInFlightFactId(null);
    }
  }

  const busy = inFlightFactId !== null;

  return (
    <div
      data-testid="company-fact-approval-console"
      role="dialog"
      aria-modal="true"
      aria-label="회사 지식 승인"
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
      <div style={{ background: '#fff', borderRadius: 10, padding: 20, width: 'min(880px, 96vw)', maxHeight: '92vh', overflow: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>회사 지식 승인</h2>
          <button onClick={onClose} aria-label="닫기" style={{ marginLeft: 'auto' }}>
            닫기
          </button>
        </div>
        <p style={{ marginTop: 0, color: '#475569', fontSize: 13 }}>
          후보로 등록된 회사 지식을 검토하고, 등록된 팀장/관리자 인증으로 승인 또는 폐기합니다.
        </p>

        {/* 인증 영역 */}
        <section style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12, marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>관리자 인증</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              Admin ID digest
              <input
                aria-label="Admin ID digest"
                value={form.adminIdDigest}
                onChange={event => setForm(s => ({ ...s, adminIdDigest: event.target.value }))}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              Admin session digest
              <input
                aria-label="Admin session digest"
                value={form.adminSessionDigest}
                onChange={event => setForm(s => ({ ...s, adminSessionDigest: event.target.value }))}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              인증 방식
              <select
                aria-label="Admin auth method"
                value={form.authMethod}
                onChange={event => setForm(s => ({ ...s, authMethod: event.target.value }))}
              >
                <option value="tauri_secure_invoke">tauri_secure_invoke</option>
                <option value="os_keychain">os_keychain</option>
              </select>
            </label>
            <div>
              <button data-testid="apply-auth-btn" onClick={handleApplyAuth}>
                인증 적용
              </button>
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 13 }} data-testid="auth-status">
            {admin ? (
              <span style={{ color: '#15803D' }}>관리자로 인증됨</span>
            ) : (
              <span style={{ color: '#9A3412' }}>인증되지 않음</span>
            )}
          </div>
          {authError && (
            <div role="alert" style={{ marginTop: 8, color: '#B91C1C', fontSize: 13 }}>
              {authError}
            </div>
          )}
        </section>

        {/* status */}
        {status && (
          <div data-testid="company-fact-status" style={{ marginBottom: 12, fontSize: 13, color: '#334155' }}>
            사용 중 {status.active_count}개 · 승인 대기 {status.candidate_count}개
          </div>
        )}

        {admin && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* 목록 */}
            <section style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                <div style={{ fontWeight: 600 }}>후보 목록</div>
                <button
                  data-testid="refresh-list-btn"
                  onClick={() => admin && refreshListAndStatus(admin)}
                  style={{ marginLeft: 'auto' }}
                  disabled={listLoading}
                >
                  새로고침
                </button>
              </div>
              {listLoading && <div data-testid="list-loading">불러오는 중…</div>}
              {listError && (
                <div role="alert" style={{ color: '#B91C1C', fontSize: 13 }}>
                  {listError}
                </div>
              )}
              {candidates && candidates.length === 0 && !listLoading && <div style={{ fontSize: 13 }}>후보가 없습니다.</div>}
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
                {(candidates ?? []).map(row => (
                  <li key={row.fact_id}>
                    <button
                      data-testid={`candidate-row-${row.fact_id}`}
                      onClick={() => handleSelectCandidate(row.fact_id)}
                      style={{ width: '100%', textAlign: 'left', padding: 8, border: '1px solid #E2E8F0', borderRadius: 6, cursor: 'pointer' }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{fieldText(row.category)}</div>
                      <div style={{ fontSize: 12, color: '#64748B' }}>
                        상태: {statusLabel(row.status)}
                      </div>
                      {row.known_bad?.known_bad_suspected && (
                        <div
                          data-testid={`known-bad-badge-${row.fact_id}`}
                          style={{ marginTop: 6, color: '#B45309', fontSize: 12, fontWeight: 600 }}
                        >
                          재검토 필요
                        </div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            {/* 상세 */}
            <section style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>상세</div>
              {detailLoading && <div data-testid="detail-loading">불러오는 중…</div>}
              {detailError && (
                <div role="alert" style={{ color: '#B91C1C', fontSize: 13 }}>
                  {detailError}
                </div>
              )}
              {detail && !detailLoading && (
                <div data-testid="candidate-detail" style={{ fontSize: 13, display: 'grid', gap: 6 }}>
                  <Row label="상태" value={statusLabel(detail.status)} />
                  <Row label="분류" value={fieldText(detail.category)} />
                  <Row label="예상 질문" value={listText(detail.question_patterns)} />
                  <Row label="필수 핵심어" value={listText(detail.keywords_required)} />
                  <Row label="관련 핵심어" value={listText(detail.keywords_any)} />
                  <Row label="출처" value={fieldText(detail.source)} />
                  <Row label="출처 링크" value={fieldText(detail.source_url)} />
                  <Row label="출처 문서" value={fieldText(detail.source_doc)} />
                  <Row label="확인 날짜" value={fieldText(detail.verified_at)} />
                  <Row label="만료일" value={fieldText(detail.expires_at)} />
                  <Row label="신뢰도" value={fieldText(detail.confidence)} />
                  {detail.known_bad?.known_bad_suspected && (
                    <KnownBadWarningPanel
                      factId={detail.fact_id}
                      disabled={busy}
                      showOverride={knownBadBlockedFactId === detail.fact_id}
                      onOverride={() => handleOverrideAndApprove(detail.fact_id)}
                    />
                  )}
                  <div style={{ marginTop: 6 }}>
                    <div style={{ color: '#64748B' }}>답변 내용</div>
                    <div data-testid="answer-runtime-text" style={{ whiteSpace: 'pre-wrap', background: '#F8FAFC', borderRadius: 6, padding: 8 }}>
                      {detail.answer_runtime_text}
                    </div>
                  </div>

                  {actionError && (
                    <div role="alert" style={{ color: '#B91C1C' }}>
                      {actionError}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <button
                      data-testid="approve-btn"
                      disabled={busy}
                      onClick={() => setConfirmTarget({ kind: 'approve', factId: detail.fact_id })}
                    >
                      승인
                    </button>
                    <button
                      data-testid="deprecate-btn"
                      disabled={busy}
                      onClick={() => {
                        setDeprecateReason('MANUAL_DEPRECATED');
                        setConfirmTarget({ kind: 'deprecate', factId: detail.fact_id });
                      }}
                    >
                      폐기
                    </button>
                    {busy && <span style={{ color: '#64748B' }}>처리 중…</span>}
                  </div>
                </div>
              )}
            </section>
          </div>
        )}

        {sessionActiveFact && (
          <section
            data-testid="session-active-fact-panel"
            style={{ border: '1px solid #BBF7D0', borderRadius: 8, padding: 12, marginTop: 12, background: '#F0FDF4' }}
          >
            <div style={{ fontWeight: 700, marginBottom: 6 }}>방금 승인한 회사 지식</div>
            <div style={{ fontSize: 13, color: '#166534', marginBottom: 8 }}>
              이번에 승인한 항목만 바로 수정하거나 사용 중지할 수 있습니다.
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button data-testid="open-supersede-btn" disabled={busy} onClick={() => openSupersedeModal(sessionActiveFact)}>
                교체
              </button>
              <button
                data-testid="active-deprecate-btn"
                disabled={busy}
                onClick={() => {
                  setDeprecateReason('SUPERSEDED');
                  setConfirmTarget({ kind: 'deprecate', factId: sessionActiveFact.fact_id });
                }}
              >
                폐기
              </button>
            </div>
          </section>
        )}

        {/* 확인 모달 */}
        {confirmTarget && (
          <div
            data-testid="confirm-modal"
            role="alertdialog"
            aria-modal="true"
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 10001,
              background: 'rgba(15,23,42,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ background: '#fff', borderRadius: 10, padding: 20, width: 'min(440px, 92vw)' }}>
              <p style={{ marginTop: 0 }}>{CONFIRM_TEXT[confirmTarget.kind]}</p>
              {confirmTarget.kind === 'deprecate' && (
                <div style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
                  <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
                    폐기 사유
                    <select
                      data-testid="deprecate-reason-select"
                      value={deprecateReason}
                      onChange={event => setDeprecateReason(event.target.value as DeprecateReasonCode)}
                    >
                      <option value="WRONG">{DEPRECATE_REASON_DISPLAY.WRONG}</option>
                      <option value="SUPERSEDED">{DEPRECATE_REASON_DISPLAY.SUPERSEDED}</option>
                      <option value="MANUAL_DEPRECATED">{DEPRECATE_REASON_DISPLAY.MANUAL_DEPRECATED}</option>
                    </select>
                  </label>
                  <div data-testid="deprecate-reason-copy" style={{ fontSize: 12, color: '#475569' }}>
                    {DEPRECATE_REASON_HELP[deprecateReason]}
                  </div>
                </div>
              )}
              {confirmTarget.kind === 'approve' && knownBadBlockedFactId === confirmTarget.factId && (
                <div style={{ border: '1px solid #FDE68A', background: '#FFFBEB', borderRadius: 8, padding: 10, marginBottom: 12 }}>
                  <div style={{ color: '#92400E', fontSize: 13, fontWeight: 700 }}>{KNOWN_BAD_WARNING_TEXT}</div>
                  <button
                    data-testid="override-and-approve-btn"
                    style={{ marginTop: 8 }}
                    disabled={busy}
                    onClick={() => handleOverrideAndApprove(confirmTarget.factId)}
                  >
                    관리자가 확인하고 승인
                  </button>
                </div>
              )}
              {actionError && (
                <div role="alert" style={{ color: '#B91C1C', fontSize: 13, marginBottom: 12 }}>
                  {actionError}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button data-testid="confirm-cancel-btn" onClick={() => setConfirmTarget(null)}>
                  취소
                </button>
                <button data-testid="confirm-ok-btn" onClick={handleConfirm} disabled={busy}>
                  확인
                </button>
              </div>
            </div>
          </div>
        )}
        {supersedeTarget && supersedeForm && (
          <SupersedeModal
            form={supersedeForm}
            error={supersedeError}
            busy={busy}
            onChange={setSupersedeForm}
            onCancel={() => {
              setSupersedeTarget(null);
              setSupersedeForm(null);
              setSupersedeError(null);
            }}
            onSubmit={handleSupersedeSubmit}
          />
        )}
      </div>
    </div>
  );
}

function KnownBadWarningPanel({
  factId,
  disabled,
  showOverride,
  onOverride,
}: {
  factId: string;
  disabled: boolean;
  showOverride: boolean;
  onOverride: () => void;
}) {
  return (
    <div
      data-testid={`known-bad-warning-${factId}`}
      style={{ border: '1px solid #FDE68A', background: '#FFFBEB', borderRadius: 8, padding: 10, marginTop: 6 }}
    >
      <div style={{ color: '#92400E', fontSize: 13, fontWeight: 700 }}>{KNOWN_BAD_WARNING_TEXT}</div>
      {showOverride && (
        <button data-testid="detail-override-and-approve-btn" style={{ marginTop: 8 }} disabled={disabled} onClick={onOverride}>
          관리자가 확인하고 승인
        </button>
      )}
    </div>
  );
}

function SupersedeModal({
  form,
  error,
  busy,
  onChange,
  onCancel,
  onSubmit,
}: {
  form: SupersedeFormState;
  error: string | null;
  busy: boolean;
  onChange: (next: SupersedeFormState) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  function update<K extends keyof SupersedeFormState>(key: K, value: SupersedeFormState[K]): void {
    onChange({ ...form, [key]: value });
  }

  return (
    <div
      data-testid="supersede-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="supersede-title"
      aria-describedby="supersede-description"
      onKeyDown={event => {
        if (event.key === 'Escape') onCancel();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10002,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div style={{ background: '#fff', borderRadius: 10, padding: 20, width: 'min(640px, 94vw)', maxHeight: '90vh', overflow: 'auto' }}>
        <h3 id="supersede-title" style={{ marginTop: 0 }}>사용 중인 회사 지식 수정</h3>
        <p id="supersede-description" style={{ color: '#475569', fontSize: 13 }}>
          신뢰도는 입력하지 않아도 됩니다. 수정한 지식은 항상 가장 높은 신뢰도로 저장됩니다.
        </p>
        <div style={{ display: 'grid', gap: 8 }}>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            분류
            <input value={form.category} onChange={event => update('category', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            예상 질문 (줄바꿈으로 2개 이상)
            <textarea value={form.questionPatterns} onChange={event => update('questionPatterns', event.target.value)} rows={3} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            필수 핵심어
            <input value={form.keywordsRequired} onChange={event => update('keywordsRequired', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            관련 핵심어
            <input value={form.keywordsAny} onChange={event => update('keywordsAny', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            답변 내용
            <textarea value={form.answerRuntimeText} onChange={event => update('answerRuntimeText', event.target.value)} rows={5} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            출처
            <input value={form.source} onChange={event => update('source', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            출처 링크
            <input value={form.sourceUrl} onChange={event => update('sourceUrl', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            출처 문서
            <input value={form.sourceDoc} onChange={event => update('sourceDoc', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            확인 날짜
            <input value={form.verifiedAt} onChange={event => update('verifiedAt', event.target.value)} placeholder="YYYY-MM-DD" />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
            만료일
            <input value={form.expiresAt} onChange={event => update('expiresAt', event.target.value)} placeholder="YYYY-MM-DD" />
          </label>
        </div>
        {error && (
          <div role="alert" style={{ color: '#B91C1C', fontSize: 13, marginTop: 10 }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button data-testid="supersede-cancel-btn" onClick={onCancel}>취소</button>
          <button data-testid="supersede-submit-btn" disabled={busy} onClick={onSubmit}>교체 실행</button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: 8 }}>
      <span style={{ color: '#64748B' }}>{label}</span>
      <span>{value}</span>
    </div>
  );
}
