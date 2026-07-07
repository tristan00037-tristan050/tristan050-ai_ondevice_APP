import React, { useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, ClipboardList, X } from 'lucide-react';
import {
  createBox6FormFill,
  isBox6SecretLikeMapping,
  type Box6Confidence,
  type Box6FormFillResult,
} from '../../lib/box6/box6FormFillClient';
import { formatFileSize, MAX_FILES, MAX_CHARS_PER_FILE, MAX_TOTAL_CHARS } from '../../lib/cards/fileText';
import { ModalFrame } from './ModalFrame';

type Props = {
  onClose: () => void;
};

function confidenceColor(confidence: Box6Confidence): { bg: string; fg: string; label: string } {
  if (confidence === 'HIGH') return { bg: '#DCFCE7', fg: '#166534', label: 'HIGH' };
  if (confidence === 'UNFILLED') return { bg: '#F1F5F9', fg: '#475569', label: 'UNFILLED' };
  return { bg: '#FEF3C7', fg: '#92400E', label: confidence };
}

function ConfidenceBadge({ confidence }: { confidence: Box6Confidence }) {
  const color = confidenceColor(confidence);
  return (
    <span style={{ borderRadius: 999, padding: '2px 8px', background: color.bg, color: color.fg, fontSize: 12, fontWeight: 700 }}>
      {color.label}
    </span>
  );
}

function safeExcerpt(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > 120 ? `${normalized.slice(0, 120)}...` : normalized;
}

function ResultPanel({ result }: { result: Box6FormFillResult }) {
  return (
    <section data-testid="box6-result" style={{ marginTop: 18, border: '1px solid #D8DEE8', borderRadius: 8, padding: 16, background: '#FFFFFF' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#14532D', fontWeight: 700 }}>
        <CheckCircle2 size={18} aria-hidden /> 양식 채우기 결과
      </div>
      <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 6, padding: 12, maxHeight: 220, overflow: 'auto' }}>
        {result.filled_form}
      </pre>

      <div style={{ overflowX: 'auto', marginTop: 14 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {['항목', '기입값', '신뢰도', '근거', '검토'].map(header => (
                <th key={header} style={{ textAlign: 'left', borderBottom: '1px solid #CBD5E1', padding: '8px 6px', color: '#334155' }}>
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.field_mappings.map((mapping, index) => {
              const isUnfilled = mapping.confidence === 'UNFILLED' || !mapping.output_value.trim();
              const isSecret = isBox6SecretLikeMapping(mapping) || result.unfilled_fields.includes(mapping.target_label);
              return (
                <tr key={`${mapping.target_label}-${index}`}>
                  <td style={{ borderBottom: '1px solid #E2E8F0', padding: '8px 6px', verticalAlign: 'top' }}>{mapping.target_label}</td>
                  <td style={{ borderBottom: '1px solid #E2E8F0', padding: '8px 6px', verticalAlign: 'top' }}>
                    {isUnfilled ? '미기입' : mapping.output_value}
                  </td>
                  <td style={{ borderBottom: '1px solid #E2E8F0', padding: '8px 6px', verticalAlign: 'top' }}>
                    <ConfidenceBadge confidence={mapping.confidence} />
                  </td>
                  <td style={{ borderBottom: '1px solid #E2E8F0', padding: '8px 6px', verticalAlign: 'top', color: '#475569' }}>
                    {safeExcerpt(mapping.source_ref || mapping.reason_code)}
                  </td>
                  <td style={{ borderBottom: '1px solid #E2E8F0', padding: '8px 6px', verticalAlign: 'top', color: isSecret || isUnfilled ? '#92400E' : '#166534' }}>
                    {isSecret || isUnfilled ? '검토 필요' : '자동 기입'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {result.unfilled_fields.length > 0 && (
        <p style={{ margin: '12px 0 0', color: '#475569', fontSize: 13 }}>
          미기입 항목: {result.unfilled_fields.join(', ')}
        </p>
      )}
      {result.warnings.length > 0 && (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18, color: '#92400E', fontSize: 13 }}>
          {result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
        </ul>
      )}
    </section>
  );
}

export function FormFillModal({ onClose }: Props) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [blankForm, setBlankForm] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<Box6FormFillResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!blankForm.trim()) {
      setError('빈 양식을 입력해 주세요.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const response = await createBox6FormFill({ blankForm, files, signal: ctrl.signal });
      setResult(response.result);
    } catch (caught) {
      if (caught instanceof Error && caught.name === 'AbortError') return;
      setError(caught instanceof Error ? caught.message : '양식 채우기에 실패했습니다.');
    } finally {
      setSubmitting(false);
      abortRef.current = null;
    }
  }

  return (
    <ModalFrame labelledBy="box6-title" testId="box6-form-fill-modal" onClose={onClose} initialFocusRef={titleRef}>
      <section style={{ width: 'min(1040px, 100%)', maxHeight: '92vh', overflow: 'auto', background: '#FFFFFF', borderRadius: 8, padding: 24, boxShadow: '0 20px 60px rgba(15, 23, 42, 0.24)' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <ClipboardList size={24} aria-hidden />
          <div style={{ flex: 1 }}>
            <h2 id="box6-title" ref={titleRef} tabIndex={-1} style={{ margin: 0, fontSize: 20 }}>상대 양식에 우리 자료 채우기</h2>
            <p style={{ margin: '4px 0 0', color: '#64748B', fontSize: 13 }}>온디바이스 · 외부전송 0 · 불확실 항목은 미기입</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 6, padding: 6, cursor: 'pointer' }}>
            <X size={18} aria-hidden />
          </button>
        </header>

        <form onSubmit={submit} style={{ display: 'grid', gap: 14 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontWeight: 700 }}>빈 양식</span>
            <textarea
              data-testid="box6-blank-form-input"
              value={blankForm}
              onChange={event => setBlankForm(event.target.value)}
              rows={8}
              placeholder="채워야 할 외부 양식의 빈 항목을 붙여넣으세요."
              style={{ width: '100%', resize: 'vertical', border: '1px solid #CBD5E1', borderRadius: 6, padding: 10, font: 'inherit' }}
            />
          </label>

          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontWeight: 700 }}>우리 자료 첨부</span>
            <input
              data-testid="box6-file-input"
              type="file"
              multiple
              accept=".txt,.md,.csv,.json,.yaml,.yml,.xml,.html,text/*,application/json"
              onChange={event => setFiles(Array.from(event.target.files ?? []))}
            />
          </label>

          {files.length > 0 && (
            <ul aria-label="첨부 파일 목록" style={{ margin: 0, paddingLeft: 18, color: '#475569', fontSize: 13 }}>
              {files.slice(0, MAX_FILES).map(file => <li key={`${file.name}-${file.size}`}>{file.name} · {formatFileSize(file.size)}</li>)}
              {files.length > MAX_FILES && <li>추가 {files.length - MAX_FILES}개 파일은 제한으로 제외됩니다.</li>}
            </ul>
          )}

          <p style={{ margin: 0, color: '#64748B', fontSize: 12 }}>
            첨부 제한: 최대 {MAX_FILES}개 · 파일당 {MAX_CHARS_PER_FILE.toLocaleString()}자 · 총 {MAX_TOTAL_CHARS.toLocaleString()}자. PDF/DOCX/이미지는 원문 미리보기 없이 제외됩니다.
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" onClick={onClose} disabled={submitting} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 6, padding: '8px 14px', cursor: 'pointer' }}>닫기</button>
            <button type="submit" data-testid="box6-submit-btn" disabled={submitting || !blankForm.trim()} aria-disabled={submitting || !blankForm.trim()} style={{ border: 'none', background: '#10367D', color: '#FFFFFF', borderRadius: 6, padding: '8px 14px', cursor: submitting ? 'wait' : 'pointer', fontWeight: 700 }}>
              {submitting ? '채우는 중...' : '양식 채우기'}
            </button>
          </div>
        </form>

        {error && (
          <div role="alert" data-testid="box6-error" style={{ marginTop: 14, border: '1px solid #F59E0B', background: '#FFFBEB', borderRadius: 8, padding: 12, color: '#92400E' }}>
            <AlertTriangle size={16} aria-hidden /> {error}
          </div>
        )}

        {result && <ResultPanel result={result} />}
      </section>
    </ModalFrame>
  );
}
