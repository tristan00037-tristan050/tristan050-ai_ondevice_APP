import React, { useState } from 'react';
import {
  approveCompanyFactCandidate,
  deprecateCompanyFact,
  getCompanyFactCandidate,
  getCompanyFactsStatus,
  listCompanyFactCandidates,
} from '../../lib/company_fact/client';
import type {
  AdminContextForSidecar,
  CompanyFactCandidateDetail,
  CompanyFactCandidateIndexEntry,
  CompanyFactsStatusResponse,
} from '../../lib/company_fact/contracts';
import {
  getExistingAdminContextForA2,
  type ExistingAdminContextInput,
} from '../../lib/admin_policy/adminContext';

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
  deprecate: '이 후보를 폐기하시겠습니까? 기록은 남지만 공식 답변에는 사용되지 않습니다.',
} as const;

function fieldText(value: string | number | null): string {
  if (value === null || value === undefined) return '—';
  return String(value);
}

function listText(values: string[]): string {
  return values && values.length > 0 ? values.join(', ') : '—';
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
  const [inFlightFactId, setInFlightFactId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
    setConfirmTarget(null);
    setInFlightFactId(factId);
    setActionError(null);
    try {
      if (kind === 'approve') {
        await approveCompanyFactCandidate(factId, admin);
      } else {
        await deprecateCompanyFact(factId, admin);
      }
      // 성공 후 목록/status 재조회 + 상세 재조회.
      await refreshListAndStatus(admin);
      await handleSelectCandidate(factId);
    } catch (error) {
      setActionError(uiErrorMessage(error));
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
              <span style={{ color: '#15803D' }}>인증 적용됨 (role: admin)</span>
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
            ACTIVE {status.active_count} · CANDIDATE {status.candidate_count}
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
                        {row.fact_id} · {row.status}
                      </div>
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
                  <Row label="fact_id" value={fieldText(detail.fact_id)} />
                  <Row label="status" value={fieldText(detail.status)} />
                  <Row label="category" value={fieldText(detail.category)} />
                  <Row label="question_patterns" value={listText(detail.question_patterns)} />
                  <Row label="keywords_required" value={listText(detail.keywords_required)} />
                  <Row label="keywords_any" value={listText(detail.keywords_any)} />
                  <Row label="source" value={fieldText(detail.source)} />
                  <Row label="source_doc" value={fieldText(detail.source_doc)} />
                  <Row label="verified_at" value={fieldText(detail.verified_at)} />
                  <Row label="expires_at" value={fieldText(detail.expires_at)} />
                  <Row label="confidence" value={fieldText(detail.confidence)} />
                  <div style={{ marginTop: 6 }}>
                    <div style={{ color: '#64748B' }}>answer_runtime_text</div>
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
                      onClick={() => setConfirmTarget({ kind: 'deprecate', factId: detail.fact_id })}
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
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button data-testid="confirm-cancel-btn" onClick={() => setConfirmTarget(null)}>
                  취소
                </button>
                <button data-testid="confirm-ok-btn" onClick={handleConfirm}>
                  확인
                </button>
              </div>
            </div>
          </div>
        )}
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
