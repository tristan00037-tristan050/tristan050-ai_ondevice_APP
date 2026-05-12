import React, { useCallback, useRef, useState } from 'react';
import { save as tauriSave } from '@tauri-apps/plugin-dialog';
import { writeFile as tauriWriteFile } from '@tauri-apps/plugin-fs';
import {
  Inbox,
  X,
  Clipboard,
  Paperclip,
  ThumbsUp,
  ThumbsDown,
  AlertCircle,
  Calendar,
  Download,
  Copy,
  AlertTriangle,
  MessageCircle,
  RotateCw,
  Loader2,
} from 'lucide-react';
import { SIDECAR_BASE } from '../../constants';

interface RequestParsingModalProps {
  onClose: () => void;
}

interface Card1Action {
  action_text: string;
  source_evidence: string;
  confidence: number;
}

// Card1Extraction 결과 형식 (알고리즘 팀 §6 — 단계 8 통합)
interface ParseResult {
  intent: string;
  intent_type: string;
  deadline: string | null;
  deadline_raw: string;
  materials: string[];
  actions: Card1Action[];
  sentence_type: string;
  confidence: number;
  confidence_band: 'auto' | 'badge' | 'confirm' | 'blocked';
  needs_review: boolean;
  reason_code: string;
  masked_text?: string;
  input_format?: string;
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'processing'; phaseNum: number; status: string }
  | { kind: 'done'; resultId: string; result: ParseResult }
  | { kind: 'error'; message: string };

// §6-6 confidence_band → 배지 스타일
const BAND_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  auto:    { bg: '#dcfce7', text: '#15803d', label: '자동 적용' },
  badge:   { bg: '#dbeafe', text: '#1d4ed8', label: '확인 배지' },
  confirm: { bg: '#fef3c7', text: '#92400e', label: '사용자 확인 필요' },
  blocked: { bg: '#fee2e2', text: '#b91c1c', label: '자동 적용 X' },
};

const INTENT_LABELS: Record<string, string> = {
  request: '요청',
  report: '보고',
  question: '질문',
  command: '지시',
  schedule: '일정',
  no_action: '조치 없음',
  unknown: '미분류',
};

const ACCEPT_FORMATS = '.txt,.md,.docx,.pdf,.eml';

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

// DocumentTransformModal 패턴 동일 — 인라인 style 영역 일관성 (단계 8.3)
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#eab308' : '#f97316';
  const label = pct >= 80 ? '높음' : pct >= 60 ? '보통' : '낮음';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px' }}>
      <span style={{ color: '#6b7280', whiteSpace: 'nowrap' }}>분석 신뢰도</span>
      <div style={{ flex: 1, backgroundColor: '#e5e7eb', borderRadius: '4px', height: '8px', minWidth: '80px' }}>
        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: '4px', transition: 'width 0.3s ease' }} />
      </div>
      <span style={{ fontWeight: 600, color: '#111827', whiteSpace: 'nowrap' }}>{pct}% ({label})</span>
    </div>
  );
}

export function RequestParsingModal({ onClose }: RequestParsingModalProps) {
  const [text, setText] = useState('');
  const [selectedFileName, setSelectedFileName] = useState<string>('');
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setSelectedFileName(file.name);
    const ext = (file.name.split('.').pop() ?? '').toLowerCase();
    if (ext === 'txt' || ext === 'md') {
      const reader = new FileReader();
      reader.onload = () => setText(reader.result as string);
      reader.readAsText(file, 'utf-8');
    } else if (ext === 'docx' || ext === 'pdf' || ext === 'eml') {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setPhase({ kind: 'processing', phaseNum: 1, status: `파일 텍스트 추출 중 (.${ext})` });
      setFeedback(null);
      try {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch(`${SIDECAR_BASE}/request_parsing/parse_file_stream`, {
          method: 'POST',
          body: form,
          signal: ctrl.signal,
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }));
          setPhase({ kind: 'error', message: (err as { detail?: string }).detail ?? resp.statusText });
          return;
        }
        const reader2 = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader2.read();
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
              const d = parsed.data as { result_id: string; result: ParseResult };
              setPhase({ kind: 'done', resultId: d.result_id, result: d.result });
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
    } else {
      setPhase({ kind: 'error', message: `.${ext} 파일은 지원되지 않습니다. (.txt .md .docx .pdf .eml)` });
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handlePaste = useCallback(() => {
    navigator.clipboard.readText().then((t) => setText((prev) => prev + t));
  }, []);

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase({ kind: 'processing', phaseNum: 1, status: 'PII 마스킹 중...' });
    setFeedback(null);

    try {
      const resp = await fetch(`${SIDECAR_BASE}/request_parsing/parse_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed, input_format: 'text' }),
        signal: ctrl.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
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
            const d = parsed.data as { result_id: string; result: ParseResult };
            setPhase({ kind: 'done', resultId: d.result_id, result: d.result });
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
  }, [text]);

  const handleCancel = () => {
    abortRef.current?.abort();
    setPhase({ kind: 'idle' });
  };

  const handleFeedback = async (value: 'positive' | 'negative') => {
    if (phase.kind !== 'done') return;
    setFeedback(value);
    await fetch(`${SIDECAR_BASE}/request_parsing/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_id: phase.resultId, feedback: value }),
    }).catch(() => {});
  };

  const handleDownloadMd = async () => {
    if (phase.kind !== 'done') return;
    try {
      const savePath = await tauriSave({
        defaultPath: 'butler_parse_result.md',
        filters: [{ name: 'Markdown', extensions: ['md'] }],
      });
      if (!savePath) return;
      const resp = await fetch(`${SIDECAR_BASE}/request_parsing/result/${phase.resultId}/markdown`);
      const bytes = new Uint8Array(await resp.arrayBuffer());
      await tauriWriteFile(savePath, bytes);
    } catch (err) {
      console.error('md download error', err);
    }
  };

  const handleDownloadDocx = async () => {
    if (phase.kind !== 'done') return;
    try {
      const savePath = await tauriSave({
        defaultPath: 'butler_parse_result.docx',
        filters: [{ name: 'Word', extensions: ['docx'] }],
      });
      if (!savePath) return;
      const resp = await fetch(`${SIDECAR_BASE}/request_parsing/result/${phase.resultId}/docx`);
      const bytes = new Uint8Array(await resp.arrayBuffer());
      await tauriWriteFile(savePath, bytes);
    } catch (err) {
      console.error('docx download error', err);
    }
  };

  const handleCopy = async () => {
    if (phase.kind !== 'done') return;
    try {
      const resp = await fetch(`${SIDECAR_BASE}/request_parsing/result/${phase.resultId}/markdown`);
      const md = await resp.text();
      await navigator.clipboard.writeText(md);
    } catch (err) {
      console.error('copy error', err);
    }
  };

  const canAnalyze = text.trim().length >= 15;

  return (
    /* ── 오버레이 (인라인 style — AccountingModal 동일 패턴, Tauri WebView 호환) ── */
    <div
      data-testid="request-parsing-modal"
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
      {/* ── 다이얼로그 컨테이너 ── */}
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          width: '100%',
          maxWidth: '896px',
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
            <Inbox size={22} style={{ color: '#2563eb' }} />
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#111827', margin: 0 }}>요청 핵심 파악·정리</h2>
              <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '2px', marginBottom: 0 }}>메일·메시지를 붙여넣으면 핵심 액션을 정리해 드립니다</p>
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

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: 'auto' }}>

          {/* ── Input area ── */}
          {phase.kind === 'idle' && (
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

              {/* Textarea zone */}
              <div
                style={{ border: '2px dashed #e5e7eb', borderRadius: '12px', padding: '16px', backgroundColor: '#f9fafb' }}
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
              >
                <textarea
                  rows={15}
                  style={{
                    width: '100%',
                    minHeight: '400px',
                    resize: 'vertical',
                    fontSize: '14px',
                    lineHeight: '1.6',
                    color: '#374151',
                    background: 'transparent',
                    border: 'none',
                    outline: 'none',
                    fontFamily: 'inherit',
                    boxSizing: 'border-box',
                  }}
                  placeholder={'메일·메시지를 여기에 붙여넣거나 파일을 드래그하세요\n(.txt .md .docx .pdf .eml 지원)'}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </div>

              {/* Character count */}
              <p style={{ textAlign: 'right', fontSize: '12px', color: text.length > 3800 ? '#f97316' : '#9ca3af', fontWeight: text.length > 3800 ? 600 : 400, margin: 0 }}>
                {text.length.toLocaleString()} / 4,000
              </p>

              {/* Buttons */}
              <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {/* 1순위: 클립보드 붙여넣기 — primary */}
                <button
                  data-testid="clipboard-paste-btn"
                  onClick={handlePaste}
                  style={{
                    width: '100%',
                    padding: '14px 24px',
                    backgroundColor: '#2563eb',
                    color: 'white',
                    border: 'none',
                    borderRadius: '12px',
                    fontSize: '15px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  <Clipboard size={18} />
                  클립보드 붙여넣기
                </button>

                {/* 2순위: 파일 첨부 — secondary */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    width: '100%',
                    padding: '12px 24px',
                    backgroundColor: '#f3f4f6',
                    color: '#374151',
                    border: '1px solid #e5e7eb',
                    borderRadius: '12px',
                    fontSize: '14px',
                    fontWeight: 500,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  <Paperclip size={16} />
                  파일 첨부 (.txt · .md · .docx · .pdf · .eml)
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT_FORMATS}
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                />

                {/* File state */}
                {selectedFileName ? (
                  <p style={{ fontSize: '13px', color: '#4b5563', margin: 0 }}>
                    선택됨: <strong>{selectedFileName}</strong>
                  </p>
                ) : (
                  <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>선택된 파일 X</p>
                )}
              </div>
            </div>
          )}

          {/* ── Processing ── */}
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
                minHeight: '300px',
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

              {/* 4-step indicator with ✓ for completed steps */}
              <div
                data-testid="progress-steps"
                style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: '320px' }}
              >
                {[1, 2, 3, 4].map((n, idx) => (
                  <React.Fragment key={n}>
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
                    {idx < 3 && (
                      <div style={{
                        flex: 1,
                        height: '3px',
                        backgroundColor: n < phase.phaseNum ? '#2563eb' : '#e5e7eb',
                      }} />
                    )}
                  </React.Fragment>
                ))}
              </div>

              {/* linear progress bar */}
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
                style={{
                  padding: '10px 24px',
                  border: '1.5px solid #d1d5db',
                  borderRadius: '10px',
                  background: 'white',
                  color: '#374151',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                취소
              </button>
            </div>
          )}

          {/* ── Result (Card1Extraction §6 — 단계 8.3 UI 영역 재구성) ── */}
          {phase.kind === 'done' && (
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <ConfidenceBar value={phase.result.confidence} />

              {/* §6-6 confidence_band + needs_review 배지 */}
              {(() => {
                const band = phase.result.confidence_band ?? 'confirm';
                const st = BAND_STYLE[band] ?? BAND_STYLE.confirm;
                return (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{
                      padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: 600,
                      backgroundColor: st.bg, color: st.text,
                    }}>
                      {st.label}
                    </span>
                    {phase.result.needs_review && (
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: '6px',
                        backgroundColor: '#fffbeb', border: '1px solid #fcd34d',
                        borderRadius: '8px', padding: '4px 10px',
                      }}>
                        <AlertTriangle size={13} style={{ color: '#d97706', flexShrink: 0 }} />
                        <span style={{ fontSize: '12px', color: '#92400e', fontWeight: 500 }}>검토 필요</span>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Intent 카드 */}
              <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <MessageCircle size={14} style={{ color: '#64748b', flexShrink: 0 }} />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>발신자 의도</span>
                  <span style={{
                    marginLeft: 'auto', padding: '2px 10px', borderRadius: '9999px',
                    fontSize: '11px', fontWeight: 600,
                    backgroundColor: '#e0e7ff', color: '#3730a3',
                  }}>
                    {INTENT_LABELS[phase.result.intent_type] ?? phase.result.intent_type}
                  </span>
                </div>
                <p style={{ fontSize: '14px', color: '#111827', fontWeight: 500, lineHeight: 1.5, margin: 0 }}>
                  {phase.result.intent}
                </p>
              </div>

              {/* Deadline 카드 */}
              {phase.result.deadline_raw && (
                <div style={{
                  backgroundColor: '#fffbeb', border: '1px solid #fcd34d',
                  borderRadius: '10px', padding: '14px 16px',
                  display: 'flex', alignItems: 'flex-start', gap: '10px',
                }}>
                  <Calendar size={18} style={{ color: '#d97706', flexShrink: 0, marginTop: '1px' }} />
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: '12px', fontWeight: 600, color: '#92400e', margin: 0 }}>마감일</p>
                    <p style={{ fontSize: '14px', color: '#111827', fontWeight: 500, marginTop: '2px', marginBottom: 0 }}>
                      {phase.result.deadline_raw}
                    </p>
                    {phase.result.deadline && (
                      <p style={{ fontSize: '12px', color: '#a16207', marginTop: '2px', marginBottom: 0 }}>
                        {phase.result.deadline}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Actions 카드 */}
              {phase.result.actions.length > 0 && (
                <div style={{ backgroundColor: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: '10px', padding: '14px 16px' }}>
                  <p style={{ fontSize: '12px', fontWeight: 600, color: '#0c4a6e', marginTop: 0, marginBottom: '10px' }}>
                    액션 목록 ({phase.result.actions.length}건)
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {phase.result.actions.map((action, i) => (
                      <div key={i} style={{
                        backgroundColor: 'white', border: '1px solid #e0f2fe',
                        borderRadius: '8px', padding: '10px 12px',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                          <AlertCircle size={14} style={{ color: '#0284c7', flexShrink: 0, marginTop: '2px' }} />
                          <p style={{ flex: 1, fontSize: '13px', color: '#111827', lineHeight: 1.5, margin: 0 }}>
                            {action.action_text}
                          </p>
                          <span style={{
                            fontSize: '11px', fontWeight: 600, whiteSpace: 'nowrap',
                            padding: '2px 8px', borderRadius: '9999px',
                            backgroundColor: action.confidence >= 0.75 ? '#dcfce7' : '#fef3c7',
                            color: action.confidence >= 0.75 ? '#15803d' : '#92400e',
                          }}>
                            {Math.round(action.confidence * 100)}%
                          </span>
                        </div>
                        {action.source_evidence && action.source_evidence !== action.action_text && (
                          <p style={{
                            fontSize: '11px', color: '#94a3b8', marginTop: '6px', marginLeft: '22px',
                            marginBottom: 0, fontStyle: 'italic',
                          }}>
                            "{action.source_evidence.slice(0, 80)}"
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Materials 카드 */}
              <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <Paperclip size={14} style={{ color: '#64748b', flexShrink: 0 }} />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>필요 자료</span>
                  {phase.result.materials.length > 0 && (
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                      ({phase.result.materials.length}건)
                    </span>
                  )}
                </div>
                {phase.result.materials.length === 0 ? (
                  <p style={{ fontSize: '13px', color: '#94a3b8', fontStyle: 'italic', margin: 0 }}>
                    필요 자료 명시 X
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {phase.result.materials.map((mat, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
                        <span style={{ color: '#cbd5e1', fontWeight: 700 }}>•</span>
                        <span style={{ color: '#334155' }}>{mat}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Feedback */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                paddingTop: '8px', borderTop: '1px solid #f3f4f6',
              }}>
                <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>결과가 도움이 되었나요?</p>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => handleFeedback('positive')}
                    aria-label="도움이 됨"
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                      color: feedback === 'positive' ? '#2563eb' : '#d1d5db',
                    }}
                  >
                    <ThumbsUp size={18} />
                  </button>
                  <button
                    onClick={() => handleFeedback('negative')}
                    aria-label="도움 안 됨"
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                      color: feedback === 'negative' ? '#dc2626' : '#d1d5db',
                    }}
                  >
                    <ThumbsDown size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Error ── */}
          {phase.kind === 'error' && (
            <div style={{ padding: '48px 32px', textAlign: 'center' }}>
              <AlertTriangle size={36} style={{ color: '#f87171', margin: '0 auto 12px' }} />
              <p style={{ fontSize: '14px', fontWeight: 600, color: '#dc2626', marginBottom: '6px' }}>파싱 오류</p>
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

        {/* ── Footer ── */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid #f3f4f6', display: 'flex', gap: '8px' }}>
          {phase.kind === 'idle' && (
            <button
              onClick={handleSubmit}
              disabled={!canAnalyze}
              style={{
                flex: 1,
                width: '100%',
                padding: '16px 24px',
                backgroundColor: canAnalyze ? '#2563eb' : '#d1d5db',
                color: canAnalyze ? 'white' : '#6b7280',
                border: 'none',
                borderRadius: '12px',
                fontSize: '17px',
                fontWeight: 700,
                cursor: canAnalyze ? 'pointer' : 'not-allowed',
              }}
            >
              분석하기
            </button>
          )}
          {phase.kind === 'done' && (
            <>
              <button
                onClick={handleCopy}
                style={{
                  flex: 1, padding: '12px',
                  backgroundColor: 'white', color: '#374151',
                  border: '1.5px solid #d1d5db', borderRadius: '10px',
                  fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                }}
              >
                <Copy size={14} />
                복사
              </button>
              <button
                onClick={handleDownloadMd}
                style={{
                  flex: 1, padding: '12px',
                  backgroundColor: 'white', color: '#374151',
                  border: '1.5px solid #d1d5db', borderRadius: '10px',
                  fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                }}
              >
                <Download size={14} />
                .md
              </button>
              <button
                onClick={handleDownloadDocx}
                style={{
                  flex: 1, padding: '12px',
                  backgroundColor: '#2563eb', color: 'white',
                  border: 'none', borderRadius: '10px',
                  fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                }}
              >
                <Download size={14} />
                .docx
              </button>
              <button
                onClick={() => { setPhase({ kind: 'idle' }); setText(''); setSelectedFileName(''); }}
                style={{
                  flex: 1, padding: '12px',
                  backgroundColor: 'white', color: '#2563eb',
                  border: '1.5px solid #bfdbfe', borderRadius: '10px',
                  fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                }}
              >
                <RotateCw size={14} />
                새 분석
              </button>
            </>
          )}
          {phase.kind === 'error' && (
            <button
              onClick={onClose}
              style={{
                flex: 1, padding: '12px',
                backgroundColor: 'white', color: '#6b7280',
                border: '1px solid #e5e7eb', borderRadius: '10px',
                fontSize: '14px', cursor: 'pointer',
              }}
            >
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
