import React, { useRef, useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { save as tauriSave } from '@tauri-apps/plugin-dialog';
import { writeFile as tauriWriteFile } from '@tauri-apps/plugin-fs';
import butlerIconAnimatedUrl from '../../assets/butler-icon-animated.svg';
import { SIDECAR_BASE } from '../../constants';

interface AccountingModalProps {
  onClose: () => void;
}

type CategoryInfo = { count: number; total_amount: number };

type Phase =
  | { kind: 'idle' }
  | { kind: 'processing'; status: string; fileName: string }
  | { kind: 'done'; resultId: string; mdContent: string; rowCount: number; categoryCount: number; categories: Record<string, CategoryInfo> }
  | { kind: 'error'; message: string };

const ACCEPT = '.xlsx,.xls,.csv';
const MIN_PHASE_MS = 1500;

function parseSseBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  const eventLine = block.split('\n').find(l => l.startsWith('event:'));
  const dataLine = block.split('\n').find(l => l.startsWith('data:'));
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

export function AccountingModal({ onClose }: AccountingModalProps) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [dragging, setDragging] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastPhaseStartMs = useRef<number>(0);

  const handleFile = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!['xlsx', 'xls', 'csv'].includes(ext)) {
      setPhase({ kind: 'error', message: `.${ext} 파일은 지원되지 않습니다. .xlsx/.xls/.csv만 허용합니다.` });
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase({ kind: 'processing', status: '파일 업로드 중...', fileName: file.name });
    setReportOpen(false);

    try {
      const form = new FormData();
      form.append('file', file);

      const res = await fetch(`${SIDECAR_BASE}/accounting/classify`, {
        method: 'POST',
        body: form,
        signal: ctrl.signal,
      });

      if (!res.ok) {
        const detail = await res.text().catch(() => res.statusText);
        setPhase({ kind: 'error', message: `서버 오류 (${res.status}): ${detail}` });
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setPhase({ kind: 'error', message: '응답 스트림을 읽을 수 없습니다.' });
        return;
      }

      const decoder = new TextDecoder();
      let buf = '';
      let receivedTerminal = false;
      const abortRace = new Promise<never>((_, rej) => {
        const onAbort = () => { const e = new Error('AbortError'); e.name = 'AbortError'; rej(e); };
        if (ctrl.signal.aborted) { onAbort(); return; }
        ctrl.signal.addEventListener('abort', onAbort, { once: true });
      });
      // Suppress unhandled-rejection when abort fires while not inside a Promise.race window
      void abortRace.catch(() => {});

      while (true) {
        const { done, value } = await reader.read();
        if (ctrl.signal.aborted) return;
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split('\n\n');
        buf = blocks.pop() ?? '';

        for (const block of blocks) {
          const parsed = parseSseBlock(block);
          if (!parsed) continue;
          const { event, data } = parsed;

          if (event === 'phase_start') {
            // Ensure previous phase is visible for MIN_PHASE_MS before switching
            const sinceLast = Date.now() - lastPhaseStartMs.current;
            if (lastPhaseStartMs.current > 0 && sinceLast < MIN_PHASE_MS) {
              await Promise.race([
                new Promise<void>(r => setTimeout(r, MIN_PHASE_MS - sinceLast)),
                abortRace,
              ]);
            }
            if (ctrl.signal.aborted) return;
            lastPhaseStartMs.current = Date.now();
            setPhase(prev => ({
              kind: 'processing',
              status: (data.status_message as string) ?? '처리 중...',
              fileName: prev.kind === 'processing' ? prev.fileName : '',
            }));
          } else if (event === 'complete') {
            receivedTerminal = true;
            // 최소 표시 시간 보장: 마지막 phase_start로부터 MIN_PHASE_MS 경과 후 전환
            const elapsed = Date.now() - lastPhaseStartMs.current;
            if (elapsed < MIN_PHASE_MS) {
              await Promise.race([
                new Promise<void>(r => setTimeout(r, MIN_PHASE_MS - elapsed)),
                abortRace,
              ]);
            }
            if (ctrl.signal.aborted) return;
            const summary = data.summary as { categories: Record<string, CategoryInfo> } | null;
            setPhase({
              kind: 'done',
              resultId: (data.result_id as string) ?? '',
              mdContent: (data.md_content as string) ?? '',
              rowCount: (data.row_count as number) ?? 0,
              categoryCount: (data.category_count as number) ?? 0,
              categories: summary?.categories ?? {},
            });
            return;
          } else if (event === 'error') {
            receivedTerminal = true;
            setPhase({ kind: 'error', message: (data.message as string) ?? '알 수 없는 오류' });
            return;
          }
        }
      }

      if (!receivedTerminal) {
        setPhase({ kind: 'error', message: '연결이 예기치 않게 종료되었습니다.' });
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setPhase({ kind: 'error', message: err instanceof Error ? err.message : '요청 오류' });
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  // Tauri v2 표준 다운로드: plugin-dialog save() + plugin-fs writeFile()
  const handleDownload = useCallback(async () => {
    if (phase.kind !== 'done') return;
    try {
      const res = await fetch(`${SIDECAR_BASE}/accounting/result/${phase.resultId}/xlsx`);
      if (!res.ok) {
        setPhase({ kind: 'error', message: `다운로드 오류 (${res.status})` });
        return;
      }
      const buffer = await res.arrayBuffer();
      if (buffer.byteLength < 1000) {
        setPhase({ kind: 'error', message: `다운로드 오류: 분류 결과 파일을 받지 못했습니다 (수신 크기: ${buffer.byteLength}B)` });
        return;
      }
      const filePath = await tauriSave({
        defaultPath: 'butler_accounting_result.xlsx',
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      });
      if (filePath) {
        await tauriWriteFile(filePath, new Uint8Array(buffer));
      }
    } catch (err: unknown) {
      setPhase({ kind: 'error', message: err instanceof Error ? err.message : '다운로드 오류' });
    }
  }, [phase]);

  const handleClose = () => {
    abortRef.current?.abort();
    onClose();
  };

  return (
    <div
      data-testid="accounting-modal-overlay"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={e => { if (e.target === e.currentTarget) handleClose(); }}
    >
      <div
        data-testid="accounting-modal"
        style={{
          background: 'var(--color-bg-app)',
          borderRadius: 16,
          width: 520,
          maxWidth: '92vw',
          maxHeight: '85vh',
          overflowY: 'auto',
          padding: 'var(--space-6)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.24)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-4)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
              💰 통장·거래내역 → 회계 분류
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
              .xlsx / .xls / .csv 파일을 업로드하면 중소기업회계기준 계정과목으로 자동 분류합니다
            </p>
          </div>
          <button
            data-testid="accounting-modal-close"
            onClick={handleClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 20, color: 'var(--color-text-secondary)', padding: '4px 8px',
            }}
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        {/* Upload zone */}
        {phase.kind === 'idle' && (
          <div
            data-testid="accounting-drop-zone"
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragging ? 'var(--color-brand-primary)' : 'var(--color-border-subtle)'}`,
              borderRadius: 12,
              padding: 'var(--space-8)',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragging ? 'rgba(16,54,125,0.04)' : 'var(--color-bg-input)',
              transition: 'border-color 150ms, background 150ms',
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 'var(--space-2)' }}>📂</div>
            <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', fontWeight: 500 }}>
              파일을 여기로 드래그하거나 클릭해서 선택
            </p>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
              .xlsx · .xls · .csv 지원
            </p>
            <input
              ref={fileInputRef}
              data-testid="accounting-file-input"
              type="file"
              accept={ACCEPT}
              onChange={handleInputChange}
              style={{ display: 'none' }}
            />
          </div>
        )}

        {/* Processing */}
        {phase.kind === 'processing' && (
          <div
            data-testid="accounting-processing"
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-6) 0' }}
          >
            {/* 첨부 파일 표시 + 삭제 버튼 */}
            <div
              data-testid="accounting-selected-file"
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 12px',
                background: 'var(--color-bg-input)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 8,
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-primary)',
                maxWidth: '100%',
              }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                📄 {phase.fileName}
              </span>
              <button
                data-testid="accounting-file-delete-btn"
                aria-label="첨부 파일 삭제"
                onClick={() => { abortRef.current?.abort(); setPhase({ kind: 'idle' }); }}
                style={{
                  flexShrink: 0,
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 16, lineHeight: 1,
                  color: 'var(--color-text-secondary)',
                  padding: '0 2px',
                }}
              >
                ×
              </button>
            </div>
            {/* 애니메이션: perspective + backfaceVisibility로 WKWebView 블러 방지 */}
            <div style={{ width: 80, height: 80, perspective: '1000px' }}>
              <img
                src={butlerIconAnimatedUrl}
                width={80}
                height={80}
                alt=""
                aria-hidden="true"
                data-testid="accounting-loading-icon"
                style={{
                  display: 'block',
                  transform: 'translateZ(0)',
                  backfaceVisibility: 'hidden',
                  WebkitBackfaceVisibility: 'hidden',
                  filter: 'none',
                } as React.CSSProperties}
              />
            </div>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
              {phase.status}
            </span>
          </div>
        )}

        {/* Error */}
        {phase.kind === 'error' && (
          <div data-testid="accounting-error" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <p style={{ margin: 0, color: 'var(--color-error)', fontSize: 'var(--text-sm)' }}>
              오류: {phase.message}
            </p>
            <button
              data-testid="accounting-retry-btn"
              onClick={() => setPhase({ kind: 'idle' })}
              style={{
                alignSelf: 'flex-start',
                padding: '6px 14px', fontSize: 'var(--text-sm)',
                background: 'var(--color-bg-input)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 8, cursor: 'pointer',
                color: 'var(--color-text-primary)',
              }}
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Result */}
        {phase.kind === 'done' && (
          <div data-testid="accounting-result" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{
              padding: 'var(--space-3)',
              background: 'rgba(15,123,15,0.06)',
              border: '1px solid rgba(15,123,15,0.2)',
              borderRadius: 8,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ color: 'var(--color-success)', fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                  ✓ 분류 완료
                </span>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                  {phase.rowCount}건 · {phase.categoryCount}개 계정과목
                </span>
              </div>
              {/* 계정과목 분류 결과 표 */}
              {Object.keys(phase.categories).length > 0 && (() => {
                const entries = Object.entries(phase.categories)
                  .sort(([, a], [, b]) => {
                    const aIsNeg = a.total_amount < 0 ? 1 : 0;
                    const bIsNeg = b.total_amount < 0 ? 1 : 0;
                    if (aIsNeg !== bIsNeg) return aIsNeg - bIsNeg;
                    return Math.abs(b.total_amount) - Math.abs(a.total_amount) || b.count - a.count;
                  });
                const totalCount = Object.values(phase.categories).reduce((s, v) => s + v.count, 0);
                const totalAmount = Object.values(phase.categories).reduce((s, v) => s + v.total_amount, 0);
                const hasAmt = entries.some(([, v]) => v.total_amount !== 0);
                return (
                  <div
                    data-testid="accounting-category-summary"
                    style={{ marginTop: 8, overflowX: 'auto' }}
                  >
                    <table
                      data-testid="accounting-category-table"
                      style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}
                    >
                      <thead>
                        <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                          <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>분류과목</th>
                          <th style={{ textAlign: 'right', padding: '4px 8px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>건수</th>
                          {hasAmt && <th style={{ textAlign: 'right', padding: '4px 8px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>합계금액</th>}
                          <th style={{ textAlign: 'center', padding: '4px 8px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>비율</th>
                        </tr>
                      </thead>
                      <tbody>
                        {entries.map(([name, info]) => {
                          const ratio = totalCount > 0 ? (info.count / totalCount * 100).toFixed(1) : '0.0';
                          return (
                            <tr key={name} style={{ borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                              <td style={{ padding: '4px 8px' }}>{name}</td>
                              <td style={{ padding: '4px 8px', textAlign: 'right' }}>{info.count}건</td>
                              {hasAmt && (
                                <td style={{
                                  padding: '4px 8px',
                                  textAlign: 'right',
                                  color: info.total_amount < 0 ? 'var(--color-accounting-debit)' : 'inherit',
                                }}>
                                  {info.total_amount !== 0 ? `${info.total_amount.toLocaleString()}원` : '-'}
                                </td>
                              )}
                              <td style={{ padding: '4px 8px', textAlign: 'center' }}>{ratio}%</td>
                            </tr>
                          );
                        })}
                      </tbody>
                      <tfoot>
                        <tr style={{ borderTop: '2px solid var(--color-border-subtle)', fontWeight: 600 }}>
                          <td style={{ padding: '4px 8px' }}>합계</td>
                          <td style={{ padding: '4px 8px', textAlign: 'right' }}>{totalCount}건</td>
                          {hasAmt && (
                            <td style={{
                              padding: '4px 8px',
                              textAlign: 'right',
                              color: totalAmount < 0 ? 'var(--color-accounting-debit)' : 'inherit',
                            }}>
                              {totalAmount !== 0 ? `${totalAmount.toLocaleString()}원` : '-'}
                            </td>
                          )}
                          <td style={{ padding: '4px 8px', textAlign: 'center' }}>100%</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                );
              })()}
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
              <button
                data-testid="accounting-download-btn"
                onClick={handleDownload}
                style={{
                  padding: '8px 16px', fontSize: 'var(--text-sm)', fontWeight: 600,
                  background: 'var(--color-brand-primary)', color: '#fff',
                  border: 'none', borderRadius: 8, cursor: 'pointer',
                }}
              >
                📥 다운로드 .xlsx
              </button>
              <button
                data-testid="accounting-report-toggle"
                onClick={() => setReportOpen(o => !o)}
                style={{
                  padding: '8px 16px', fontSize: 'var(--text-sm)',
                  background: 'var(--color-bg-input)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 8, cursor: 'pointer',
                  color: 'var(--color-text-primary)',
                }}
              >
                {reportOpen ? '보고서 닫기' : '보고서 보기'}
              </button>
              <button
                onClick={() => setPhase({ kind: 'idle' })}
                style={{
                  padding: '8px 16px', fontSize: 'var(--text-sm)',
                  background: 'none',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 8, cursor: 'pointer',
                  color: 'var(--color-text-secondary)',
                }}
              >
                새 파일
              </button>
            </div>

            {reportOpen && (
              <div
                data-testid="accounting-report-content"
                style={{
                  padding: 'var(--space-4)',
                  background: 'var(--color-bg-input)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 8,
                  fontSize: 'var(--text-sm)',
                  lineHeight: 1.7,
                  color: 'var(--color-text-primary)',
                }}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table({ node: _node, children, ...props }) {
                      return <table {...props} style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12, marginBottom: 12 }}>{children}</table>;
                    },
                    thead({ node: _node, children, ...props }) {
                      return <thead {...props} style={{ background: 'var(--color-bg-elevated)', borderBottom: '2px solid var(--color-border-subtle)' }}>{children}</thead>;
                    },
                    th({ node: _node, children, ...props }) {
                      return <th {...props} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--color-text-primary)' }}>{children}</th>;
                    },
                    td({ node: _node, children, ...props }) {
                      const text = String(Array.isArray(children) ? children.join('') : (children ?? ''));
                      const isDebit = /^-[\d,]+원$/.test(text.trim());
                      const isNumeric = /^-?[\d,]+/.test(text.trim());
                      const style: React.CSSProperties = {
                        padding: '6px 12px',
                        borderTop: '1px solid var(--color-border-subtle)',
                        fontVariantNumeric: 'tabular-nums',
                        textAlign: isNumeric ? 'right' : 'left',
                        ...(isDebit ? { color: 'var(--color-accounting-debit)' } : {}),
                      };
                      return <td {...props} style={style}>{children}</td>;
                    },
                  }}
                >
                  {phase.mdContent}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
