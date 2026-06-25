import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, FilePlus, X } from 'lucide-react';
import {
  createBox3Draft,
  validateBox3DraftRequest,
  type Box3DraftResponse,
  type Box3FormatHint,
} from '../../lib/box3/box3DraftClient';

const FORMAT_HINTS: Box3FormatHint[] = ['보고서', '이메일', '계약 검토', '회의 안건', '자유형'];

function safeDraftText(response: Box3DraftResponse): string {
  return response.draft ?? response.draft_text ?? '';
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" data-testid="box3-error" style={{ border: '1px solid #F59E0B', background: '#FFFBEB', borderRadius: 8, padding: 12 }}>
      <AlertTriangle size={16} aria-hidden /> {message}
    </div>
  );
}

export function Box3DraftModal({ onClose }: { onClose: () => void }) {
  const [referenceText, setReferenceText] = useState('');
  const [draftingRequest, setDraftingRequest] = useState('');
  const [formatHint, setFormatHint] = useState<Box3FormatHint>('자유형');
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState<Box3DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleReferenceFile(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    const chunks: string[] = [];
    for (const file of files.slice(0, 5)) {
      const text = await file.text();
      chunks.push(text.slice(0, 20000));
    }
    setReferenceText(chunks.join('\\n\\n---\\n\\n'));
    event.target.value = '';
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    const request = {
      reference_docs: [referenceText].filter(text => text.trim()),
      drafting_request: draftingRequest,
      format_hint: formatHint,
      max_new_tokens: 512,
    };
    const errors = validateBox3DraftRequest(request);
    if (errors.length) {
      setError(errors[0]);
      return;
    }
    setSubmitting(true);
    try {
      const result = await createBox3Draft(request);
      setResponse(result);
    } catch (caught) {
      const err = caught as { failClass?: string; message?: string };
      setError(err.failClass || err.message || '박스3 초안 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="box3-title" data-testid="box3-draft-modal" style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(15,23,42,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <section style={{ width: 'min(980px, 100%)', maxHeight: '92vh', overflow: 'auto', background: '#fff', borderRadius: 12, padding: 24 }}>
        <header style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
          <FilePlus size={24} aria-hidden />
          <div style={{ flex: 1 }}>
            <h2 id="box3-title" style={{ margin: 0 }}>기존 문서 기반 새 초안</h2>
            <p style={{ margin: '4px 0 0', color: '#64748B', fontSize: 13 }}>v9.2-r2b 번들 활성화 경로 · /v1/cards/3/draft 전용 호출</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 8, padding: 6 }}>
            <X size={18} aria-hidden />
          </button>
        </header>

        <form onSubmit={submit} style={{ display: 'grid', gap: 14 }}>
          <label>
            과거 참고 문서
            <textarea
              aria-label="과거 참고 문서"
              value={referenceText}
              onChange={event => setReferenceText(event.target.value)}
              rows={9}
              placeholder="참고할 과거 문서 내용을 붙여넣으세요. 원문은 요청 runtime에만 사용됩니다."
              style={{ width: '100%' }}
            />
          </label>
          <label>
            텍스트 파일 불러오기
            <input aria-label="과거 문서 파일" type="file" multiple accept=".txt,.md,.csv" onChange={handleReferenceFile} />
          </label>
          <label>
            새 상황·요구사항
            <textarea
              aria-label="새 상황"
              value={draftingRequest}
              onChange={event => setDraftingRequest(event.target.value)}
              rows={5}
              placeholder="새 초안에 반영할 상황과 요구사항을 입력하세요."
              style={{ width: '100%' }}
            />
          </label>
          <label>
            초안 유형
            <select aria-label="초안 유형" value={formatHint} onChange={event => setFormatHint(event.target.value as Box3FormatHint)}>
              {FORMAT_HINTS.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <button type="submit" disabled={submitting} data-testid="box3-submit-btn">
            {submitting ? '생성 중...' : '초안 생성'}
          </button>
        </form>

        {error && <div style={{ marginTop: 14 }}><ErrorBox message={error} /></div>}

        {response && (
          <section data-testid="box3-result" style={{ marginTop: 18, border: '1px solid #E2E8F0', borderRadius: 10, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#14532D', fontWeight: 700 }}>
              <CheckCircle2 size={18} aria-hidden /> 응답 수신
            </div>
            <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 6, fontSize: 12 }}>
              <dt>status</dt><dd>{response.status ?? 'unknown'}</dd>
              <dt>fail_class</dt><dd>{response.fail_class ?? '없음'}</dd>
              <dt>request_digest</dt><dd style={{ overflowWrap: 'anywhere' }}>{response.request_digest ?? '없음'}</dd>
              <dt>raw_doc_logged</dt><dd>{String(response.raw_doc_logged === false)}</dd>
            </dl>
            <h3>초안</h3>
            <pre style={{ whiteSpace: 'pre-wrap', background: '#F8FAFC', padding: 12, borderRadius: 8 }}>{safeDraftText(response) || '(초안 없음)'}</pre>
            {response.citations && response.citations.length > 0 && (
              <>
                <h3>근거</h3>
                <ul>
                  {response.citations.map((citation, index) => (
                    <li key={index}>{Object.entries(citation).map(([k, v]) => `${k}: ${v}`).join(' / ')}</li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}
      </section>
    </div>
  );
}
