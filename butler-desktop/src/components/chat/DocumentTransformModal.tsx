/**
 * @deprecated D-4 Card2 v1.1 — `src/components/v1_1/Card2DocumentTransform.tsx` 로 대체됨.
 * App.tsx 는 더 이상 본 컴포넌트를 사용하지 않는다. 기존 테스트 호환을 위해
 * 파일만 유지하며, P3~P11 잔여 큐의 테스트 마이그레이션 후 제거 예정.
 */
import React, { useCallback, useRef, useState } from 'react';
import { save as tauriSave } from '@tauri-apps/plugin-dialog';
import { writeFile as tauriWriteFile } from '@tauri-apps/plugin-fs';
import {
  ArrowRightLeft,
  X,
  Upload,
  ThumbsUp,
  ThumbsDown,
  Download,
  RotateCw,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { SIDECAR_BASE } from '../../constants';

interface DocumentTransformModalProps {
  onClose: () => void;
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'processing'; phaseNum: number; status: string }
  | { kind: 'done'; resultId: string; summary: TransformSummary }
  | { kind: 'error'; message: string };

interface SlotResult {
  slot_id: string;
  heading: string;
  confidence: number;
  needs_review: boolean;
  mapped: boolean;
}

interface TransformSummary {
  confidence: number;
  mapped_count: number;
  total_count: number;
  unmapped_sections: string[];
  slot_results?: SlotResult[];
  needs_review?: boolean;
}

const ACCEPT_EXTERNAL = '.txt,.md,.docx,.pdf,.eml';
const ACCEPT_TEMPLATE = '.docx,.md';

function parseSseBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  const eventLine = block.split('\n').find((l) => l.startsWith('event:'));
  const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
  if (!dataLine) return null;
  try {
    return {
      event: eventLine?.slice(6).trim() ?? 'unknown',
      data: JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#eab308' : '#f97316';
  const label = pct >= 80 ? '높음' : pct >= 60 ? '보통' : '낮음';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px' }}>
      <span style={{ color: '#6b7280', whiteSpace: 'nowrap' }}>변환 신뢰도</span>
      <div style={{ flex: 1, backgroundColor: '#e5e7eb', borderRadius: '4px', height: '8px', minWidth: '80px' }}>
        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: '4px', transition: 'width 0.3s ease' }} />
      </div>
      <span style={{ fontWeight: 600, color: '#111827', whiteSpace: 'nowrap' }}>{pct}% ({label})</span>
    </div>
  );
}

function FileDropZone({
  label,
  accept,
  testId,
  fileName,
  onFile,
}: {
  label: string;
  accept: string;
  testId: string;
  fileName: string;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      style={{
        border: `2px dashed ${dragging ? '#2563eb' : '#d1d5db'}`,
        borderRadius: '10px',
        padding: '16px',
        backgroundColor: dragging ? 'rgba(37,99,235,0.04)' : '#f9fafb',
        transition: 'border-color 150ms ease-out',
        cursor: 'pointer',
      }}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files[0];
        if (f) onFile(f);
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Upload size={18} style={{ color: '#9ca3af', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: '13px', fontWeight: 600, color: '#374151', margin: 0 }}>{label}</p>
          {fileName ? (
            <p style={{ fontSize: '12px', color: '#2563eb', margin: '2px 0 0' }}>
              <CheckCircle2 size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
              {fileName}
            </p>
          ) : (
            <p style={{ fontSize: '12px', color: '#9ca3af', margin: '2px 0 0' }}>
              클릭하거나 드래그하여 파일 선택 ({accept})
            </p>
          )}
        </div>
        <button
          data-testid={testId}
          onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
          style={{
            padding: '6px 12px',
            backgroundColor: '#f3f4f6',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 500,
            color: '#374151',
            cursor: 'pointer',
          }}
        >
          {fileName ? '변경' : '선택'}
        </button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        data-accept={accept}
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
    </div>
  );
}

export function DocumentTransformModal({ onClose }: DocumentTransformModalProps) {
  const [externalFile, setExternalFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [includeSourceNote, setIncludeSourceNote] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const canTransform = externalFile !== null && templateFile !== null && phase.kind === 'idle';

  const handleTransform = useCallback(async () => {
    if (!externalFile || !templateFile) return;

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase({ kind: 'processing', phaseNum: 1, status: '외부 문서 분석 중...' });
    setFeedback(null);

    const MAX_RETRIES = 1;
    const RETRY_DELAY_MS = 2000;

    let resp: Response | null = null;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      if (attempt > 0) {
        // 첫 호출 실패 시 자동 재시도 (sidecar 첫 기동 cold-start 대응)
        setPhase({ kind: 'processing', phaseNum: 1, status: `분석 엔진 연결 재시도 중... (${attempt}/${MAX_RETRIES})` });
        await new Promise<void>(r => setTimeout(r, RETRY_DELAY_MS));
        if (ctrl.signal.aborted) return;
      }
      try {
        const form = new FormData();
        form.append('external_file', externalFile);
        form.append('template_file', templateFile);
        form.append('include_source_note', String(includeSourceNote));
        resp = await fetch(`${SIDECAR_BASE}/document_transform/transform_stream`, {
          method: 'POST',
          body: form,
          signal: ctrl.signal,
        });
        break; // 성공 시 루프 탈출
      } catch (err: unknown) {
        if ((err as { name?: string }).name === 'AbortError') return;
        if (attempt >= MAX_RETRIES) {
          setPhase({ kind: 'error', message: '분석 엔진에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.' });
          return;
        }
        // 재시도
      }
    }

    if (!resp) return;

    try {
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp!.statusText }));
        setPhase({ kind: 'error', message: (err as { detail?: string }).detail ?? resp.statusText });
        return;
      }

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split('\n\n');
        buf = blocks.pop() ?? '';
        for (const block of blocks) {
          const parsed = parseSseBlock(block);
          if (!parsed) continue;
          if (parsed.event === 'phase_start') {
            const d = parsed.data as { phase?: number; status_message?: string };
            setPhase({ kind: 'processing', phaseNum: d.phase ?? 1, status: d.status_message ?? '처리 중...' });
          } else if (parsed.event === 'complete') {
            const d = parsed.data as { result_id: string; summary: TransformSummary };
            setPhase({ kind: 'done', resultId: d.result_id, summary: d.summary });
          } else if (parsed.event === 'error') {
            const d = parsed.data as { message?: string };
            setPhase({ kind: 'error', message: d.message ?? '알 수 없는 오류' });
          }
        }
      }
    } catch (err: unknown) {
      if ((err as { name?: string }).name === 'AbortError') return;
      setPhase({ kind: 'error', message: String(err) });
    }
  }, [externalFile, templateFile, includeSourceNote]);

  const handleCancel = () => {
    abortRef.current?.abort();
    setPhase({ kind: 'idle' });
  };

  const handleFeedback = async (value: 'positive' | 'negative') => {
    if (phase.kind !== 'done') return;
    setFeedback(value);
    await fetch(`${SIDECAR_BASE}/document_transform/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_id: phase.resultId, feedback: value }),
    }).catch(() => {});
  };

  const handleDownloadDocx = async () => {
    if (phase.kind !== 'done') return;
    try {
      const savePath = await tauriSave({
        defaultPath: 'butler_transform_result.docx',
        filters: [{ name: 'Word', extensions: ['docx'] }],
      });
      if (!savePath) return;
      const resp = await fetch(`${SIDECAR_BASE}/document_transform/result/${phase.resultId}/docx`);
      const bytes = new Uint8Array(await resp.arrayBuffer());
      await tauriWriteFile(savePath, bytes);
    } catch (err) {
      console.error('docx download error', err);
    }
  };

  const handleDownloadMd = async () => {
    if (phase.kind !== 'done') return;
    try {
      const savePath = await tauriSave({
        defaultPath: 'butler_transform_result.md',
        filters: [{ name: 'Markdown', extensions: ['md'] }],
      });
      if (!savePath) return;
      const resp = await fetch(`${SIDECAR_BASE}/document_transform/result/${phase.resultId}/md`);
      const bytes = new Uint8Array(await resp.arrayBuffer());
      await tauriWriteFile(savePath, bytes);
    } catch (err) {
      console.error('md download error', err);
    }
  };

  return (
    <div
      data-testid="document-transform-modal"
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          width: '100%',
          maxWidth: '800px',
          margin: '0 16px',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '85vh',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px', borderBottom: '1px solid #f3f4f6' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ArrowRightLeft size={22} style={{ color: '#2563eb' }} />
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#111827', margin: 0 }}>남의 문서 → 우리 양식</h2>
              <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '2px', marginBottom: 0 }}>외부 문서와 우리 양식을 올리면 우리 형식으로 변환해 드립니다</p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="닫기"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '6px', borderRadius: '8px', color: '#9ca3af', display: 'flex' }}
          >
            <X size={22} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto' }}>

          {/* Idle — file upload */}
          {phase.kind === 'idle' && (
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <FileDropZone
                label="외부 문서 (남의 문서)"
                accept={ACCEPT_EXTERNAL}
                testId="external-file-input-btn"
                fileName={externalFile?.name ?? ''}
                onFile={setExternalFile}
              />
              <FileDropZone
                label="우리 양식 (과거 작성본)"
                accept={ACCEPT_TEMPLATE}
                testId="template-file-input-btn"
                fileName={templateFile?.name ?? ''}
                onFile={setTemplateFile}
              />

              {/* Options */}
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#374151', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={includeSourceNote}
                  onChange={(e) => setIncludeSourceNote(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: '#2563eb' }}
                />
                원본 출처 각주 추가
              </label>
            </div>
          )}

          {/* Processing */}
          {phase.kind === 'processing' && (
            <div
              data-testid="loading-container"
              style={{
                padding: '48px 32px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '24px',
                minHeight: '280px',
              }}
            >
              <Loader2
                data-testid="loading-spinner"
                size={64}
                className="animate-spin"
                style={{ color: '#2563eb' }}
              />
              <div style={{ textAlign: 'center' }}>
                <p style={{ fontSize: '18px', fontWeight: 600, color: '#111827', margin: 0 }}>{phase.status}</p>
                <p style={{ fontSize: '13px', color: '#9ca3af', marginTop: '6px', marginBottom: 0 }}>단계 {phase.phaseNum} / 4</p>
              </div>

              {/* 4-step indicator */}
              <div
                data-testid="progress-steps"
                style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: '320px' }}
              >
                {['외부 문서\n분석', '양식\n구조 분석', '내용\n매핑', '문서\n생성'].map((label, idx) => {
                  const n = idx + 1;
                  return (
                    <React.Fragment key={n}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                        <div
                          data-step={n}
                          style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            backgroundColor: n <= phase.phaseNum ? '#2563eb' : '#e5e7eb',
                            color: n <= phase.phaseNum ? 'white' : '#9ca3af',
                            fontSize: '13px',
                            fontWeight: 700,
                            flexShrink: 0,
                          }}
                        >
                          {n < phase.phaseNum ? '✓' : n}
                        </div>
                      </div>
                      {idx < 3 && (
                        <div style={{ flex: 1, height: '3px', backgroundColor: n < phase.phaseNum ? '#2563eb' : '#e5e7eb' }} />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>

              <div style={{ width: '100%', maxWidth: '320px', height: '4px', backgroundColor: '#e5e7eb', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${(phase.phaseNum / 4) * 100}%`,
                  backgroundColor: '#2563eb',
                  borderRadius: '2px',
                  transition: 'width 0.3s ease',
                }} />
              </div>

              <button
                onClick={handleCancel}
                style={{ padding: '10px 24px', border: '1.5px solid #d1d5db', borderRadius: '10px', background: 'white', color: '#374151', fontSize: '14px', fontWeight: 500, cursor: 'pointer' }}
              >
                취소
              </button>
            </div>
          )}

          {/* Done */}
          {phase.kind === 'done' && (
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <ConfidenceBar value={phase.summary.confidence} />

              {/* §11 needs_review 배지 */}
              {phase.summary.needs_review && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#fffbeb', border: '1px solid #fcd34d', borderRadius: '8px', padding: '10px 14px' }}>
                  <AlertTriangle size={15} style={{ color: '#d97706', flexShrink: 0 }} />
                  <span style={{ fontSize: '13px', color: '#92400e', fontWeight: 500 }}>
                    일부 항목의 신뢰도가 낮습니다 (0.70 미만). 사용자 확인 필요
                  </span>
                </div>
              )}

              {/* Mapping summary */}
              <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '10px', padding: '14px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <CheckCircle2 size={16} style={{ color: '#16a34a' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#15803d' }}>
                    매핑 완료: {phase.summary.mapped_count} / {phase.summary.total_count} 섹션
                  </span>
                </div>
                {phase.summary.unmapped_sections.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginTop: '8px' }}>
                    <AlertCircle size={14} style={{ color: '#d97706', flexShrink: 0, marginTop: '1px' }} />
                    <span style={{ fontSize: '12px', color: '#92400e' }}>
                      미매핑 섹션: {phase.summary.unmapped_sections.join(', ')}
                    </span>
                  </div>
                )}
              </div>

              {/* 슬롯별 신뢰도 (semantic_mapping 결과) */}
              {phase.summary.slot_results && phase.summary.slot_results.length > 0 && (
                <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px 16px' }}>
                  <p style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '8px', marginTop: 0 }}>
                    항목별 매핑 신뢰도
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {phase.summary.slot_results.map((sr) => (
                      <div key={sr.slot_id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                        <span style={{ flex: 1, color: '#374151' }}>{sr.heading}</span>
                        {sr.mapped ? (
                          <>
                            <span style={{
                              padding: '2px 7px',
                              borderRadius: '9999px',
                              fontSize: '11px',
                              fontWeight: 600,
                              backgroundColor: sr.confidence >= 0.70 ? '#dcfce7' : '#fef3c7',
                              color: sr.confidence >= 0.70 ? '#15803d' : '#92400e',
                            }}>
                              {Math.round(sr.confidence * 100)}%
                            </span>
                            {sr.needs_review && (
                              <span style={{ fontSize: '11px', color: '#d97706' }}>검토 필요</span>
                            )}
                          </>
                        ) : (
                          <span style={{ fontSize: '11px', color: '#9ca3af' }}>미매핑</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Feedback */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '8px', borderTop: '1px solid #f3f4f6' }}>
                <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>변환 결과가 적합했나요?</p>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => handleFeedback('positive')}
                    aria-label="적합함"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: feedback === 'positive' ? '#2563eb' : '#d1d5db' }}
                  >
                    <ThumbsUp size={18} />
                  </button>
                  <button
                    onClick={() => handleFeedback('negative')}
                    aria-label="부적합"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: feedback === 'negative' ? '#dc2626' : '#d1d5db' }}
                  >
                    <ThumbsDown size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {phase.kind === 'error' && (
            <div style={{ padding: '48px 32px', textAlign: 'center' }}>
              <AlertTriangle size={36} style={{ color: '#f87171', margin: '0 auto 12px' }} />
              <p style={{ fontSize: '14px', fontWeight: 600, color: '#dc2626', marginBottom: '6px' }}>변환 오류</p>
              <p style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>{phase.message}</p>
              <button
                onClick={() => setPhase({ kind: 'idle' })}
                style={{ fontSize: '12px', color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                다시 시도
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid #f3f4f6', display: 'flex', gap: '8px' }}>
          {phase.kind === 'idle' && (
            <button
              onClick={handleTransform}
              disabled={!canTransform}
              style={{
                flex: 1,
                width: '100%',
                padding: '16px 24px',
                backgroundColor: canTransform ? '#2563eb' : '#d1d5db',
                color: canTransform ? 'white' : '#6b7280',
                border: 'none',
                borderRadius: '12px',
                fontSize: '17px',
                fontWeight: 700,
                cursor: canTransform ? 'pointer' : 'not-allowed',
              }}
            >
              변환하기
            </button>
          )}
          {phase.kind === 'done' && (
            <>
              <button
                onClick={handleDownloadDocx}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: '#2563eb',
                  color: 'white',
                  border: 'none',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <Download size={15} />
                .docx 다운로드
              </button>
              <button
                onClick={handleDownloadMd}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: 'white',
                  color: '#374151',
                  border: '1.5px solid #d1d5db',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <Download size={15} />
                .md 다운로드
              </button>
              <button
                onClick={() => { setPhase({ kind: 'idle' }); setExternalFile(null); setTemplateFile(null); }}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: 'white',
                  color: '#2563eb',
                  border: '1.5px solid #bfdbfe',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <RotateCw size={15} />
                새 변환
              </button>
            </>
          )}
          {phase.kind === 'error' && (
            <button
              onClick={onClose}
              style={{ flex: 1, padding: '12px', backgroundColor: 'white', color: '#6b7280', border: '1px solid #e5e7eb', borderRadius: '10px', fontSize: '14px', cursor: 'pointer' }}
            >
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
