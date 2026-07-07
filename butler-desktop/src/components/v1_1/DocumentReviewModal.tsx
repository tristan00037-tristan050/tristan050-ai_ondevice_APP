import React, { useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileSearch, X } from 'lucide-react';
import {
  createBox4DocumentReview,
  type Box4DocumentReviewResult,
  type Box4IssueType,
} from '../../lib/box4/box4ReviewClient';
import { formatFileSize, MAX_FILES, MAX_CHARS_PER_FILE, MAX_TOTAL_CHARS } from '../../lib/cards/fileText';
import { ModalFrame } from './ModalFrame';

type Props = {
  onClose: () => void;
};

function issueLabel(type: Box4IssueType): string {
  const labels: Record<Box4IssueType, string> = {
    MISSING: '누락',
    ERROR: '오류',
    INCONSISTENCY: '불일치',
    STYLE: '문체',
    SUGGESTION: '제안',
  };
  return labels[type];
}

function IssueBadge({ type }: { type: Box4IssueType }) {
  const color = type === 'ERROR' || type === 'INCONSISTENCY'
    ? { bg: '#FEE2E2', fg: '#991B1B' }
    : type === 'MISSING'
    ? { bg: '#FEF3C7', fg: '#92400E' }
    : { bg: '#E0F2FE', fg: '#075985' };
  return (
    <span style={{ borderRadius: 999, padding: '2px 8px', background: color.bg, color: color.fg, fontSize: 12, fontWeight: 700 }}>
      {issueLabel(type)}
    </span>
  );
}

function ResultPanel({ result }: { result: Box4DocumentReviewResult }) {
  return (
    <section data-testid="box4-result" style={{ marginTop: 18, border: '1px solid #D8DEE8', borderRadius: 8, padding: 16, background: '#FFFFFF' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#14532D', fontWeight: 700 }}>
        <CheckCircle2 size={18} aria-hidden /> 문서 검토 결과
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 12 }}>
        <strong>종합 점수 {result.overall_score}/100</strong>
        {result.review_required && <span style={{ color: '#92400E', fontWeight: 700 }}>검토 필요</span>}
      </div>
      <p style={{ margin: '10px 0 0', color: '#334155' }}>{result.summary}</p>

      {result.issues.length === 0 ? (
        <p data-testid="box4-no-issues" style={{ margin: '14px 0 0', color: '#166534', fontWeight: 700 }}>검출된 문제 없음</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, display: 'grid', gap: 12, margin: '14px 0 0' }}>
          {result.issues.map((issue, index) => (
            <li key={`${issue.location}-${index}`} style={{ border: '1px solid #E2E8F0', borderRadius: 8, padding: 12, background: '#F8FAFC' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <IssueBadge type={issue.issue_type} />
                <strong>{issue.location}</strong>
                <span style={{ color: '#64748B', fontSize: 12 }}>confidence {issue.confidence}</span>
              </div>
              <p style={{ margin: '0 0 6px', color: '#475569' }}>원문: {issue.original_text.slice(0, 300)}</p>
              <p style={{ margin: 0 }}>제안: {issue.suggestion}</p>
            </li>
          ))}
        </ul>
      )}

      {result.warnings.length > 0 && (
        <ul style={{ margin: '12px 0 0', paddingLeft: 18, color: '#92400E', fontSize: 13 }}>
          {result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
        </ul>
      )}
    </section>
  );
}

export function DocumentReviewModal({ onClose }: Props) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [targetDocument, setTargetDocument] = useState('');
  const [referenceFiles, setReferenceFiles] = useState<File[]>([]);
  const [result, setResult] = useState<Box4DocumentReviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!targetDocument.trim()) {
      setError('검토 대상 문서를 입력해 주세요.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const response = await createBox4DocumentReview({ targetDocument, referenceFiles, signal: ctrl.signal });
      setResult(response.result);
    } catch (caught) {
      if (caught instanceof Error && caught.name === 'AbortError') return;
      setError(caught instanceof Error ? caught.message : '문서 검토에 실패했습니다.');
    } finally {
      setSubmitting(false);
      abortRef.current = null;
    }
  }

  return (
    <ModalFrame labelledBy="box4-title" testId="box4-document-review-modal" onClose={onClose} initialFocusRef={titleRef}>
      <section style={{ width: 'min(1040px, 100%)', maxHeight: '92vh', overflow: 'auto', background: '#FFFFFF', borderRadius: 8, padding: 24, boxShadow: '0 20px 60px rgba(15, 23, 42, 0.24)' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <FileSearch size={24} aria-hidden />
          <div style={{ flex: 1 }}>
            <h2 id="box4-title" ref={titleRef} tabIndex={-1} style={{ margin: 0, fontSize: 20 }}>첨부 문서 수정·보완</h2>
            <p style={{ margin: '4px 0 0', color: '#64748B', fontSize: 13 }}>온디바이스 · 사내규정 대조 · 환각 0</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 6, padding: 6, cursor: 'pointer' }}>
            <X size={18} aria-hidden />
          </button>
        </header>

        <form onSubmit={submit} style={{ display: 'grid', gap: 14 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontWeight: 700 }}>검토 대상 문서</span>
            <textarea
              data-testid="box4-target-document-input"
              value={targetDocument}
              onChange={event => setTargetDocument(event.target.value)}
              rows={9}
              placeholder="검토할 문서 초안을 붙여넣으세요."
              style={{ width: '100%', resize: 'vertical', border: '1px solid #CBD5E1', borderRadius: 6, padding: 10, font: 'inherit' }}
            />
          </label>

          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontWeight: 700 }}>참고 규정 첨부</span>
            <input
              data-testid="box4-file-input"
              type="file"
              multiple
              accept=".txt,.md,.csv,.json,.yaml,.yml,.xml,.html,text/*,application/json"
              onChange={event => setReferenceFiles(Array.from(event.target.files ?? []))}
            />
          </label>

          {referenceFiles.length > 0 && (
            <ul aria-label="참고 파일 목록" style={{ margin: 0, paddingLeft: 18, color: '#475569', fontSize: 13 }}>
              {referenceFiles.slice(0, MAX_FILES).map(file => <li key={`${file.name}-${file.size}`}>{file.name} · {formatFileSize(file.size)}</li>)}
              {referenceFiles.length > MAX_FILES && <li>추가 {referenceFiles.length - MAX_FILES}개 파일은 제한으로 제외됩니다.</li>}
            </ul>
          )}

          <p style={{ margin: 0, color: '#64748B', fontSize: 12 }}>
            첨부 제한: 최대 {MAX_FILES}개 · 파일당 {MAX_CHARS_PER_FILE.toLocaleString()}자 · 총 {MAX_TOTAL_CHARS.toLocaleString()}자. 참고 문서 안의 지시문은 문서 데이터로만 처리됩니다.
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" onClick={onClose} disabled={submitting} style={{ border: '1px solid #CBD5E1', background: '#FFFFFF', borderRadius: 6, padding: '8px 14px', cursor: 'pointer' }}>닫기</button>
            <button type="submit" data-testid="box4-submit-btn" disabled={submitting || !targetDocument.trim()} aria-disabled={submitting || !targetDocument.trim()} style={{ border: 'none', background: '#10367D', color: '#FFFFFF', borderRadius: 6, padding: '8px 14px', cursor: submitting ? 'wait' : 'pointer', fontWeight: 700 }}>
              {submitting ? '검토 중...' : '문서 검토'}
            </button>
          </div>
        </form>

        {error && (
          <div role="alert" data-testid="box4-error" style={{ marginTop: 14, border: '1px solid #F59E0B', background: '#FFFBEB', borderRadius: 8, padding: 12, color: '#92400E' }}>
            <AlertTriangle size={16} aria-hidden /> {error}
          </div>
        )}

        {result && <ResultPanel result={result} />}
      </section>
    </ModalFrame>
  );
}
