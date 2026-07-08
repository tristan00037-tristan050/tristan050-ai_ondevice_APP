import React, { useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, FilePlus, X } from 'lucide-react';
import {
  createBox3Draft,
  validateBox3DraftRequest,
  type Box3DraftResponse,
  type Box3FormatHint,
} from '../../lib/box3/box3DraftClient';
import { MAX_CHARS_PER_FILE, prepareCardTextFiles } from '../../lib/cards/fileText';

const FORMAT_HINTS: Box3FormatHint[] = ['보고서', '이메일', '계약 검토', '회의 안건', '자유형'];

// #842(box4·box6) 검증본과 동일한 시각적 숨김 input 스타일 — 네이티브 Choose Files 미노출.
const hiddenFileInputStyle: React.CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  margin: -1,
  padding: 0,
  border: 0,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  clipPath: 'inset(50%)',
  whiteSpace: 'nowrap',
};

// prepareCardTextFiles 로 정규화된 File 의 텍스트를 읽는다(#842 재사용, 20000/60000자 제한 일관).
function readPreparedFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('FILE_READ_FAILED'));
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
    reader.readAsText(file);
  });
}

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
  const referenceFileInputRef = useRef<HTMLInputElement>(null);
  const [referenceText, setReferenceText] = useState('');
  const [draftingRequest, setDraftingRequest] = useState('');
  const [formatHint, setFormatHint] = useState<Box3FormatHint>('자유형');
  const [loadingReferenceFile, setLoadingReferenceFile] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState<Box3DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 채움형: 선택한 과거 문서 파일 1건의 텍스트로 '과거 참고 문서' textarea 를 채운다.
  // '과거 참고 문서' 는 reference_docs 단일 원소(≤ MAX_CHARS_PER_FILE)로 제출되므로,
  // box4·box6 의 main-file-load 와 동일하게 파일 1건만 불러온다. prepareCardTextFiles 가
  // 문서당 MAX_CHARS_PER_FILE 로 캡하므로 제출 검증(REFERENCE_DOC_TOO_LARGE)을 항상 만족한다.
  async function handleReferenceFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setLoadingReferenceFile(true);
    setError(null);
    try {
      const prepared = await prepareCardTextFiles([file]);
      const text = prepared.files[0]?.file ? await readPreparedFileText(prepared.files[0].file) : '';
      if (text.trim()) {
        setReferenceText(text);
      } else {
        setError('파일에서 텍스트를 추출하지 못했습니다.');
      }
    } catch {
      setError('파일에서 텍스트를 추출하지 못했습니다.');
    } finally {
      setLoadingReferenceFile(false);
    }
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
          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <label htmlFor="box3-reference-input" style={{ fontWeight: 700 }}>과거 참고 문서</label>
              <span>
                <input
                  ref={referenceFileInputRef}
                  aria-label="과거 문서 파일"
                  data-testid="box3-reference-file-input"
                  type="file"
                  accept=".txt,.md,.csv,.json,.yaml,.yml,.xml,.html,text/*,application/json"
                  onChange={handleReferenceFile}
                  tabIndex={-1}
                  style={hiddenFileInputStyle}
                />
                <button
                  type="button"
                  data-testid="box3-reference-file-load-btn"
                  onClick={() => referenceFileInputRef.current?.click()}
                  disabled={loadingReferenceFile}
                  style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 6, padding: '4px 10px', fontSize: 12, cursor: loadingReferenceFile ? 'wait' : 'pointer' }}
                >
                  {loadingReferenceFile ? '불러오는 중...' : '파일에서 불러오기'}
                </button>
              </span>
            </div>
            <span style={{ color: '#64748B', fontSize: 12 }}>
              새 초안의 바탕이 될 기존 문서(계획서·공문·보고서 등)의 내용입니다. 직접 붙여넣거나 파일에서 불러오세요.
            </span>
            <textarea
              id="box3-reference-input"
              data-testid="box3-reference-input"
              value={referenceText}
              onChange={event => setReferenceText(event.target.value)}
              rows={9}
              placeholder="예: 작년 사업계획서, 지난달 공문 등 참고할 문서 내용을 붙여넣으세요."
              style={{ width: '100%', resize: 'vertical', border: '1px solid #CBD5E1', borderRadius: 6, padding: 10, font: 'inherit' }}
            />
            <span style={{ color: '#94A3B8', fontSize: 11 }}>
              파일 1개의 텍스트로 채웁니다 · 최대 {MAX_CHARS_PER_FILE.toLocaleString()}자. PDF/DOCX/이미지는 제외됩니다.
            </span>
          </div>

          <div style={{ display: 'grid', gap: 6 }}>
            <label htmlFor="box3-request-input" style={{ fontWeight: 700 }}>새 상황·요구사항</label>
            <span style={{ color: '#64748B', fontSize: 12 }}>
              어떤 문서를 만들지와 반영할 변경사항을 적어주세요.
            </span>
            <textarea
              id="box3-request-input"
              data-testid="box3-request-input"
              value={draftingRequest}
              onChange={event => setDraftingRequest(event.target.value)}
              rows={5}
              placeholder="예: 첨부한 문서를 기반으로 2026년 사업계획서 초안을 구성해줘"
              style={{ width: '100%', resize: 'vertical', border: '1px solid #CBD5E1', borderRadius: 6, padding: 10, font: 'inherit' }}
            />
          </div>

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
