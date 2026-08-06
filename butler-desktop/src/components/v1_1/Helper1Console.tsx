import React, { useEffect, useRef, useState } from 'react';
import {
  askHelper1,
  fetchHelper1Status,
  type Helper1Answer,
  type Helper1Status,
} from '../../lib/helper1/client';
import { uiSafeSidecarErrorMessage } from '../../lib/sidecarFetch';
import { ModalFrame } from './ModalFrame';

const STATE_LABEL: Record<string, string> = {
  READY: '질문 가능',
  READY_TEST_ONLY: '시험 전용',
  ASSET_MISSING: '자산 연결 필요',
  INDEXING: '문서 색인 중',
  VERIFYING: '색인 검증 중',
  INDEX_INVALID: '색인 무결성 오류',
  STALE: '폴더 변경 감지',
  FAILED: '실행 실패',
};

const REFUSAL_LABEL: Record<string, string> = {
  REFUSED_NO_GROUNDING: '문서에서 충분한 근거를 찾지 못해 답하지 않았습니다.',
  REFUSED_ASSET_MISSING: '승인된 모델·색인이 연결되지 않아 답하지 않았습니다.',
  REFUSED_POLICY: '현재 정책 또는 권한으로는 답할 수 없습니다.',
  REFUSED_DLP: '민감정보 보호 검사에서 답변 공개가 차단됐습니다.',
  REFUSED_INJECTION: '문서 또는 질문에서 지시문 공격이 감지됐습니다.',
  REFUSED_INDEX_INVALID: '색인 무결성 검증에 실패했습니다.',
  CANCELLED: '요청이 취소됐습니다.',
  FAILED: '로컬 답변 엔진 실행에 실패했습니다.',
};

export function Helper1Console({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [status, setStatus] = useState<Helper1Status | null>(null);
  const [workspaceId, setWorkspaceId] = useState('');
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState<Helper1Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(): Promise<void> {
    setError(null);
    try {
      const next = await fetchHelper1Status();
      setStatus(next);
      const ready = next.workspaces.find(workspace => workspace.state === 'READY');
      setWorkspaceId(current => current || ready?.workspace_id || next.workspaces[0]?.workspace_id || '');
    } catch (caught) {
      setError(uiSafeSidecarErrorMessage(caught));
    }
  }

  useEffect(() => {
    void refresh();
    return () => abortRef.current?.abort();
  }, []);

  async function ask(): Promise<void> {
    if (!workspaceId || !query.trim() || busy) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await askHelper1(workspaceId, query.trim(), controller.signal));
    } catch (caught) {
      setError(uiSafeSidecarErrorMessage(caught));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
    }
  }

  const selected = status?.workspaces.find(workspace => workspace.workspace_id === workspaceId);
  const ready = selected?.state === 'READY';

  return (
    <ModalFrame
      labelledBy="helper1-console-title"
      testId="helper1-console"
      onClose={onClose}
      initialFocusRef={closeRef}
    >
      <section style={{ width: 'min(760px, 100%)', maxHeight: '88vh', overflow: 'auto', borderRadius: 16, padding: 24, background: '#fff' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <p className="eyebrow">기기 안에서만 처리</p>
            <h2 id="helper1-console-title">도우미1 · 회사 문서</h2>
          </div>
          <button ref={closeRef} onClick={onClose}>닫기</button>
        </header>

        <div role="status" style={{ padding: 12, borderRadius: 10, background: ready ? '#ecfdf5' : '#fff7ed' }}>
          <strong>{STATE_LABEL[selected?.state ?? status?.state ?? 'ASSET_MISSING'] ?? '확인 필요'}</strong>
          <p style={{ marginBottom: 0 }}>
            {ready
              ? '검증된 로컬 색인과 답변 모델이 연결되어 있습니다.'
              : '네이티브 폴더 승인·자산 봉인·색인 검증이 완료되기 전에는 답변을 만들지 않습니다.'}
          </p>
        </div>

        {status && (
          <p style={{ color: '#64748B', fontSize: 13 }}>
            외부 네트워크 {status.external_network_allowed ? '허용' : '차단'} ·
            제품 출시 {status.product_release_allowed ? '허용' : '미승인'} ·
            런타임 활성화 {status.runtime_activation_allowed ? '허용' : '미승인'}
          </p>
        )}

        {status && status.workspaces.length > 0 && (
          <label style={{ display: 'grid', gap: 6 }}>
            승인된 작업공간
            <select value={workspaceId} onChange={event => setWorkspaceId(event.target.value)}>
              {status.workspaces.map(workspace => (
                <option key={workspace.workspace_id} value={workspace.workspace_id}>
                  {workspace.workspace_id.slice(0, 8)} · {STATE_LABEL[workspace.state] ?? workspace.state}
                </option>
              ))}
            </select>
          </label>
        )}

        <label style={{ display: 'grid', gap: 6, marginTop: 16 }}>
          회사 문서에 질문
          <textarea
            value={query}
            onChange={event => setQuery(event.target.value)}
            maxLength={4000}
            rows={4}
            disabled={!ready || busy}
            placeholder={ready ? '예: 지난 분기 매출 근거를 알려 주세요.' : '검증된 작업공간이 준비되면 질문할 수 있습니다.'}
          />
        </label>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button onClick={() => void ask()} disabled={!ready || !query.trim() || busy}>
            {busy ? '근거 확인 중…' : '문서 근거로 답하기'}
          </button>
          <button onClick={() => void refresh()} disabled={busy}>상태 새로고침</button>
        </div>

        {answer && (
          <section aria-live="polite" style={{ marginTop: 18, borderTop: '1px solid #e2e8f0', paddingTop: 16 }}>
            {answer.kind === 'ANSWERED' && answer.answer
              ? <>
                  <h3>답변</h3>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</p>
                  <h4>근거</h4>
                  <ul>
                    {answer.citations.map(citation => (
                      <li key={citation.claim_id}>
                        자료 {citation.source_id.slice(0, 12)} · 근거 {citation.evidence_start}–{citation.evidence_end}
                      </li>
                    ))}
                  </ul>
                </>
              : <p role="alert">{REFUSAL_LABEL[answer.kind] ?? `답변 차단: ${answer.reason_code ?? answer.kind}`}</p>}
          </section>
        )}
        {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
      </section>
    </ModalFrame>
  );
}
