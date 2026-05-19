import React from 'react';
import { AlertTriangle, CheckCircle, Download, XCircle } from 'lucide-react';

type ConfidenceState = 'pass' | 'warn' | 'fail';

export type Card2SlotMapping = {
  slotId: string;
  title: string;
  confidence: number;
  sourceRef: string;
  status: ConfidenceState;
};

export type Card2ResultProps = {
  confidence: number;
  externalSummary: string[];
  mappings: Card2SlotMapping[];
  previewMarkdown: string;
  onDownloadDocx: () => void;
  onDownloadMd: () => void;
};

function confidenceState(confidence: number): ConfidenceState {
  if (confidence >= 0.82) return 'pass';
  if (confidence >= 0.70) return 'warn';
  return 'fail';
}

function StateIcon({ state }: { state: ConfidenceState }) {
  if (state === 'pass') return <CheckCircle aria-hidden size={16} color="var(--color-success, #375623)" />;
  if (state === 'warn') return <AlertTriangle aria-hidden size={16} color="var(--color-warning, #C55A11)" />;
  return <XCircle aria-hidden size={16} color="var(--color-danger, #C00000)" />;
}

export function Card2Result({ confidence, externalSummary, mappings, previewMarkdown, onDownloadDocx, onDownloadMd }: Card2ResultProps) {
  const state = confidenceState(confidence);
  return (
    <section data-testid="card2-result" aria-label="카드 2 변환 결과" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <StateIcon state={state} />
        <strong>결과: 우리 양식 보고서 - 신뢰도 {confidence.toFixed(2)}</strong>
        <div aria-label="신뢰도 게이지" style={{ flex: 1, height: 10, borderRadius: 999, background: '#E5E7EB', overflow: 'hidden' }}>
          <div style={{ width: `${Math.round(confidence * 100)}%`, height: '100%', background: state === 'pass' ? '#375623' : state === 'warn' ? '#C55A11' : '#C00000' }} />
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.2fr', gap: 14 }}>
        <article data-testid="external-summary-pane" style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 12, padding: 14 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>1) 외부 요약</h3>
          <ul style={{ paddingLeft: 18, marginBottom: 0 }}>{externalSummary.map((item, idx) => <li key={idx}>{item}</li>)}</ul>
        </article>

        <article data-testid="mapping-pane" style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 12, padding: 14 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>2) 항목 매핑</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mappings.map(item => (
              <div key={item.slotId} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center' }}>
                <span>{item.title} → {item.slotId}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><StateIcon state={item.status} />{item.confidence.toFixed(2)}</span>
                <small style={{ gridColumn: '1 / -1', color: 'var(--color-text-secondary)' }}>{item.sourceRef}</small>
              </div>
            ))}
          </div>
        </article>

        <article data-testid="our-result-pane" style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 12, padding: 14 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>3) 우리 결과</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13, minHeight: 160 }}>{previewMarkdown}</pre>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onDownloadDocx}><Download aria-hidden size={14} /> .docx 다운로드</button>
            <button type="button" onClick={onDownloadMd}><Download aria-hidden size={14} /> .md 다운로드</button>
          </div>
        </article>
      </div>
    </section>
  );
}
