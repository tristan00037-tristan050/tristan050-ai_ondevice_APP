import React, { useMemo, useRef, useState } from 'react';
import { ArrowRightLeft, FileText, Inbox, Loader2, Play, X } from 'lucide-react';
import { Card2Result, type Card2SlotMapping } from './Card2Result';

const EXTERNAL_ACCEPT = '.docx,.pdf,.eml,.txt,.md';
const TEMPLATE_ACCEPT = '.docx,.md';
const STEPS = ['외부 문서 핵심 추출', '우리 양식 구조 분석', '매핑 + 결합', '최종 산출물 직조'];

type StepState = 'idle' | 'running' | 'done' | 'error';

type ResultState = {
  confidence: number;
  externalSummary: string[];
  mappings: Card2SlotMapping[];
  previewMarkdown: string;
};

function UploadBox({ title, accept, icon, file, onFile }: { title: string; accept: string; icon: React.ReactNode; file: File | null; onFile: (file: File) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <button type="button" onClick={() => ref.current?.click()} data-testid={`card2-upload-${title}`} style={{ minHeight: 240, border: '2px dashed var(--color-border-subtle)', borderRadius: 16, background: 'var(--color-bg-input)', padding: 18, textAlign: 'center', cursor: 'pointer' }}>
      <input ref={ref} type="file" accept={accept} hidden onChange={event => { const picked = event.target.files?.[0]; if (picked) onFile(picked); }} />
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>{icon}</div>
      <strong>{title}</strong>
      <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>{file ? file.name : `파일 드래그 또는 클릭 (${accept})`}</p>
    </button>
  );
}

export function Card2DocumentTransform({ onClose }: { onClose: () => void }) {
  const [externalFile, setExternalFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [step, setStep] = useState(0);
  const [state, setState] = useState<StepState>('idle');
  const [result, setResult] = useState<ResultState | null>(null);

  const canStart = externalFile !== null && templateFile !== null && state !== 'running';
  const progress = useMemo(() => Math.min(100, Math.round(((step + (state === 'done' ? 1 : 0)) / 4) * 100)), [step, state]);

  async function start() {
    if (!canStart) return;
    setState('running');
    setResult(null);
    for (let i = 0; i < 4; i += 1) {
      setStep(i);
      await new Promise(resolve => setTimeout(resolve, 120));
    }
    setState('done');
    setResult({
      confidence: 0.0,
      externalSummary: ['대표 GUI 확인 전 placeholder summary', '실제 sidecar 실행 후 evidence 갱신 필요'],
      mappings: [
        { slotId: 'slot.pending.1', title: '매핑 검증 대기', confidence: 0, sourceRef: 'evidence/d4_card2/mapping_accuracy.json 필요', status: 'fail' },
      ],
      previewMarkdown: '실제 변환 결과는 sidecar endpoint 검증 후 생성됩니다. 본 컴포넌트는 v1.1 UI 계약을 고정합니다.',
    });
  }

  return (
    <div data-testid="card2-document-transform-modal" role="dialog" aria-modal="true" aria-label="남의 문서에서 우리 양식 보고서로 변환" style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={event => event.target === event.currentTarget && onClose()}>
      <section style={{ width: 'min(1100px, calc(100vw - 32px))', maxHeight: '90vh', overflow: 'auto', background: 'white', borderRadius: 18, padding: 24 }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
          <ArrowRightLeft aria-hidden size={24} />
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>남의 문서 → 우리 양식 보고서</h2>
            <p style={{ margin: '4px 0 0', color: 'var(--color-text-secondary)', fontSize: 13 }}>외부 송신 0 · raw text 로그 0 · manual review 우선</p>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose}><X aria-hidden size={20} /></button>
        </header>

        {state !== 'done' && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <UploadBox title="외부 문서" accept={EXTERNAL_ACCEPT} icon={<Inbox aria-hidden size={32} />} file={externalFile} onFile={setExternalFile} />
              <UploadBox title="우리 과거 양식" accept={TEMPLATE_ACCEPT} icon={<FileText aria-hidden size={32} />} file={templateFile} onFile={setTemplateFile} />
            </div>
            <div style={{ marginTop: 18, display: 'grid', gap: 8 }}>
              <label><input type="checkbox" defaultChecked /> 빈칸은 확인 필요로 표기</label>
              <label><input type="checkbox" defaultChecked disabled /> 민감정보 자동 마스킹</label>
            </div>
            {state === 'running' && (
              <div data-testid="card2-progress" style={{ marginTop: 20, textAlign: 'center' }}>
                <Loader2 aria-hidden className="animate-spin" size={36} />
                <p>Step {step + 1} - {STEPS[step]}</p>
                <div style={{ height: 10, background: '#E5E7EB', borderRadius: 999, overflow: 'hidden' }}><div style={{ width: `${progress}%`, height: '100%', background: 'var(--color-brand-primary)' }} /></div>
              </div>
            )}
            <button type="button" data-testid="card2-start" disabled={!canStart} onClick={start} style={{ marginTop: 20, width: '100%', padding: 16, borderRadius: 12, background: canStart ? 'var(--color-brand-primary)' : '#D1D5DB', color: 'white', fontWeight: 700 }}>
              <Play aria-hidden size={16} /> 변환 시작 (외부 송신 0)
            </button>
          </>
        )}

        {state === 'done' && result && (
          <Card2Result {...result} onDownloadDocx={() => undefined} onDownloadMd={() => undefined} />
        )}
      </section>
    </div>
  );
}
