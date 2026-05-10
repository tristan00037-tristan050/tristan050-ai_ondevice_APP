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
} from 'lucide-react';
import { SIDECAR_BASE } from '../../constants';

interface RequestParsingModalProps {
  onClose: () => void;
}

interface ActionItem {
  text: string;
  priority: 'P1' | 'P2' | 'P3';
  rationale?: string;
}

interface ParseResult {
  actions: ActionItem[];
  deadline: { raw_text: string; parsed_date: string | null; confidence: number; time_text?: string };
  required_materials: { name: string; is_optional: boolean; rationale?: string }[];
  intent: { summary: string; tone: string; expected_response: string };
  confidence: number;
  masked_text?: string;
  input_format?: string;
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'processing'; phaseNum: number; status: string }
  | { kind: 'done'; resultId: string; result: ParseResult }
  | { kind: 'error'; message: string };

const PRIORITY_COLORS: Record<string, string> = {
  P1: 'text-red-600 bg-red-50 border-red-200',
  P2: 'text-orange-600 bg-orange-50 border-orange-200',
  P3: 'text-gray-500 bg-gray-50 border-gray-200',
};

const PRIORITY_LABELS: Record<string, string> = {
  P1: 'P1 긴급',
  P2: 'P2 권장',
  P3: 'P3 선택',
};

const PRIORITY_ICON_COLORS: Record<string, string> = {
  P1: '#dc2626',
  P2: '#ea580c',
  P3: '#9ca3af',
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

function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? 'bg-green-500' : pct >= 70 ? 'bg-yellow-400' : pct >= 50 ? 'bg-orange-400' : 'bg-red-400';
  const label = pct >= 90 ? '높음' : pct >= 70 ? '보통' : pct >= 50 ? '낮음' : '불신뢰';
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-500">신뢰도</span>
      <div className="flex-1 bg-gray-200 rounded-full h-2 min-w-[80px]">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-medium text-gray-700">{pct}% ({label})</span>
    </div>
  );
}

export function RequestParsingModal({ onClose }: RequestParsingModalProps) {
  const [text, setText] = useState('');
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
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

  return (
    <div
      data-testid="request-parsing-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl mx-4 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Inbox size={20} className="text-blue-500" />
            <div>
              <h2 className="text-lg font-semibold text-gray-900">요청 핵심 파악·정리</h2>
              <p className="text-xs text-gray-400 mt-0.5">메일·메시지를 붙여넣으면 핵심 액션을 정리해 드립니다</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors" aria-label="닫기">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Input area */}
          {phase.kind === 'idle' && (
            <div className="p-5 space-y-3">
              {/* Text input zone */}
              <div
                className="border-2 border-dashed border-gray-200 rounded-xl p-4 hover:border-blue-300 transition-colors bg-gray-50/40"
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
              >
                <textarea
                  className="w-full min-h-[300px] resize-none text-sm text-gray-700 placeholder-gray-400 focus:outline-none bg-transparent leading-relaxed"
                  placeholder={'메일·메시지를 여기에 붙여넣거나 파일을 드래그하세요\n(.txt .md .docx .pdf .eml 지원)'}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </div>

              {/* Character count — always visible */}
              <p className={`text-xs text-right ${text.length > 3800 ? 'text-orange-500 font-medium' : 'text-gray-400'}`}>
                {text.length.toLocaleString()} / 4,000
              </p>

              {/* Action buttons — vertical hierarchy */}
              <div className="space-y-2 pt-1 border-t border-gray-100">
                {/* 1순위: 클립보드 붙여넣기 */}
                <button
                  onClick={handlePaste}
                  className="w-full py-3 text-sm font-semibold text-white bg-blue-500 hover:bg-blue-600 active:bg-blue-700 transition-colors rounded-xl flex items-center justify-center gap-2 shadow-sm"
                >
                  <Clipboard size={16} />
                  클립보드 붙여넣기
                </button>

                {/* 2순위: 파일 첨부 */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full py-2.5 text-sm text-gray-600 border border-gray-200 bg-white hover:bg-gray-50 transition-colors rounded-xl flex items-center justify-center gap-2"
                >
                  <Paperclip size={15} />
                  파일 첨부 (.txt · .md · .docx · .pdf · .eml)
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT_FORMATS}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                />
              </div>
            </div>
          )}

          {/* Processing */}
          {phase.kind === 'processing' && (
            <div className="p-8 flex flex-col items-center gap-4">
              <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin" />
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700">{phase.status}</p>
                <p className="text-xs text-gray-400 mt-1">단계 {phase.phaseNum}/4</p>
              </div>
              <div className="flex gap-1 mt-1">
                {[1, 2, 3, 4].map((n) => (
                  <div
                    key={n}
                    className={`w-2 h-2 rounded-full ${n <= phase.phaseNum ? 'bg-blue-500' : 'bg-gray-200'}`}
                  />
                ))}
              </div>
              <button
                onClick={handleCancel}
                className="mt-2 text-xs text-gray-400 hover:text-gray-600 underline"
              >
                취소
              </button>
            </div>
          )}

          {/* Result */}
          {phase.kind === 'done' && (
            <div className="p-5 space-y-4">
              <ConfidenceGauge value={phase.result.confidence} />

              {/* Intent */}
              <div className="bg-gray-50 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <MessageCircle size={13} className="text-gray-400 shrink-0" />
                  <p className="text-xs font-semibold text-gray-500">발신자 의도</p>
                </div>
                <p className="text-sm text-gray-800 font-medium leading-snug">{phase.result.intent.summary}</p>
                <div className="flex gap-3 mt-2 text-xs text-gray-400">
                  <span>톤: {phase.result.intent.tone}</span>
                  {phase.result.intent.expected_response && (
                    <span>기대응답: {phase.result.intent.expected_response}</span>
                  )}
                </div>
              </div>

              {/* Deadline */}
              {phase.result.deadline.raw_text && (
                <div className="bg-yellow-50 border border-yellow-100 rounded-xl p-3 flex items-start gap-2">
                  <Calendar size={18} className="text-yellow-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-yellow-700">마감일</p>
                    <p className="text-sm text-gray-800">
                      {phase.result.deadline.raw_text}
                      {phase.result.deadline.time_text ? ` ${phase.result.deadline.time_text}까지` : ''}
                    </p>
                    {(phase.result.deadline.parsed_date || phase.result.deadline.time_text) && (
                      <p className="text-xs text-yellow-600 mt-0.5">
                        {[phase.result.deadline.parsed_date, phase.result.deadline.time_text].filter(Boolean).join(' ')}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Actions */}
              {phase.result.actions.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 mb-2">액션 목록</p>
                  <div className="space-y-2">
                    {phase.result.actions.map((action, i) => (
                      <div
                        key={i}
                        className={`border rounded-xl px-3 py-2.5 ${PRIORITY_COLORS[action.priority] ?? 'text-gray-700 bg-gray-50 border-gray-200'}`}
                      >
                        <div className="flex items-start gap-2">
                          <AlertCircle
                            size={14}
                            className="shrink-0 mt-0.5"
                            style={{ color: PRIORITY_ICON_COLORS[action.priority] ?? '#9ca3af' }}
                          />
                          <span className="text-xs font-bold shrink-0">{PRIORITY_LABELS[action.priority] ?? action.priority}</span>
                          <p className="text-sm flex-1">{action.text}</p>
                        </div>
                        {action.rationale && (
                          <p className="text-xs opacity-70 mt-1 pl-10">{action.rationale}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Materials — always render */}
              <div>
                <div className="flex items-center gap-1.5 mb-2">
                  <Paperclip size={13} className="text-gray-400 shrink-0" />
                  <p className="text-xs font-semibold text-gray-500">필요 자료</p>
                </div>
                {phase.result.required_materials.length === 0 ? (
                  <p className="text-sm text-gray-400 italic">필요 자료 명시 X</p>
                ) : (
                  <div className="space-y-1">
                    {phase.result.required_materials.map((mat, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm text-gray-700 py-0.5">
                        <span className="text-gray-300">•</span>
                        <span>{mat.name}</span>
                        {mat.is_optional && (
                          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">선택</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Feedback */}
              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <p className="text-xs text-gray-400">결과가 도움이 되었나요?</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleFeedback('positive')}
                    className={`transition-transform hover:scale-110 ${feedback === 'positive' ? 'opacity-100 text-blue-500' : 'opacity-50 hover:opacity-100 text-gray-400'}`}
                    aria-label="도움이 됨"
                  >
                    <ThumbsUp size={18} />
                  </button>
                  <button
                    onClick={() => handleFeedback('negative')}
                    className={`transition-transform hover:scale-110 ${feedback === 'negative' ? 'opacity-100 text-red-500' : 'opacity-50 hover:opacity-100 text-gray-400'}`}
                    aria-label="도움 안 됨"
                  >
                    <ThumbsDown size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {phase.kind === 'error' && (
            <div className="p-6 text-center">
              <AlertTriangle size={36} className="text-red-400 mx-auto mb-3" />
              <p className="text-sm text-red-600 font-medium mb-1">파싱 오류</p>
              <p className="text-xs text-gray-500 mb-4">{phase.message}</p>
              <button
                onClick={() => setPhase({ kind: 'idle' })}
                className="text-xs text-blue-500 hover:underline"
              >
                다시 시도
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 flex gap-2">
          {phase.kind === 'idle' && (
            <button
              onClick={handleSubmit}
              disabled={text.trim().length < 30}
              className="flex-1 py-3 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 disabled:bg-gray-100 disabled:text-gray-400 text-white text-base font-semibold rounded-xl transition-colors shadow-sm disabled:shadow-none"
            >
              분석하기
            </button>
          )}
          {phase.kind === 'done' && (
            <>
              <button
                onClick={handleCopy}
                className="flex-1 py-2 text-sm text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors flex items-center justify-center gap-1.5"
              >
                <Copy size={14} />
                복사
              </button>
              <button
                onClick={handleDownloadMd}
                className="flex-1 py-2 text-sm text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors flex items-center justify-center gap-1.5"
              >
                <Download size={14} />
                .md
              </button>
              <button
                onClick={handleDownloadDocx}
                className="flex-1 py-2 text-sm text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors flex items-center justify-center gap-1.5"
              >
                <Download size={14} />
                .docx
              </button>
              <button
                onClick={() => { setPhase({ kind: 'idle' }); setText(''); }}
                className="flex-1 py-2 text-sm text-blue-500 border border-blue-200 rounded-xl hover:bg-blue-50 transition-colors flex items-center justify-center gap-1.5"
              >
                <RotateCw size={14} />
                새 분석
              </button>
            </>
          )}
          {(phase.kind === 'error') && (
            <button onClick={onClose} className="flex-1 py-2.5 text-sm text-gray-600 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors">
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
