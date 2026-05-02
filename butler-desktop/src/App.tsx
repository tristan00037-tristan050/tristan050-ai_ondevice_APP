import React, { useState, useRef, useEffect } from 'react';
import { HomeScreen } from './components/HomeScreen';
import { EgressBadge } from './components/EgressBadge';
import { InputBar } from './components/InputBar';
import { ModelSetup } from './components/ModelSetup';
import { ProgressOverlay } from './components/ProgressOverlay';
import { SIDECAR_BASE } from './constants';
import type { SSEEvent } from './types';

export function App() {
  const [sseEvents, setSseEvents] = useState<SSEEvent[]>([]);
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [cardMode, setCardMode] = useState<number | null>(null);
  const [resultText, setResultText] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (resultText && resultRef.current && typeof resultRef.current.scrollIntoView === 'function') {
      resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [resultText]);

  const handleSubmit = async (text: string, files: File[]) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setSseEvents([]);
    setResultText(null);
    setCancelReason(null);
    setOverlayVisible(true);

    try {
      const formData = new FormData();
      formData.append('query', text);
      formData.append('card_mode', String(cardMode ?? 'free'));
      formData.append('total_chunks', '1');
      files.forEach((file, idx) => formData.append(`file_${idx}`, file));
      formData.append('file_count', String(files.length));

      const res = await fetch(`${SIDECAR_BASE}/api/analyze/stream`, {
        method: 'POST',
        body: formData,
        signal: ctrl.signal,
      });
      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split('\n\n');
        buf = blocks.pop() ?? '';
        for (const block of blocks) {
          const parts = block.split('\n');
          const eventLine = parts.find(l => l.startsWith('event:'));
          const dataLine = parts.find(l => l.startsWith('data:'));
          if (dataLine) {
            const eventType = (eventLine?.slice(6).trim() ?? 'unknown') as SSEEvent['type'];
            const data = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>;
            const evt: SSEEvent = { type: eventType, data };
            setSseEvents(prev => [...prev, evt]);

            if (eventType === 'complete') {
              if (data.result_text) {
                setResultText(data.result_text as string);
              }
              setOverlayVisible(false);
              return;
            }

            if (eventType === 'cancelled') {
              setCancelReason((data.reason as string) ?? 'unknown');
              setOverlayVisible(false);
              return;
            }
          }
        }
      }
    } catch {
      setOverlayVisible(false);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setOverlayVisible(false);
    setSseEvents([]);
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 16 }}>
      <EgressBadge />
      <ModelSetup onReady={() => {}} />
      <HomeScreen onCardSelect={setCardMode}>
        <InputBar onSubmit={handleSubmit} />
      </HomeScreen>
      <ProgressOverlay
        visible={overlayVisible}
        events={sseEvents}
        onCancel={handleCancel}
        onResult={() => setOverlayVisible(false)}
      />
      {cancelReason && !overlayVisible && (
        <div style={{
          marginTop: 16,
          padding: 12,
          background: '#fff3cd',
          border: '1px solid #ffc107',
          borderRadius: 8,
          fontSize: 13,
          color: '#856404',
        }}>
          {cancelReason === 'chunk_timeout'
            ? '한 청크가 너무 오래 걸려 중단됐습니다.'
            : cancelReason === 'hard_timeout'
            ? '전체 시간 초과 (300초)로 중단됐습니다.'
            : '작업이 중단됐습니다.'}
        </div>
      )}
      {resultText && !overlayVisible && (
        <div
          ref={resultRef}
          data-testid="result-panel"
          style={{
            marginTop: 24,
            padding: 24,
            background: '#f8f9fa',
            border: '1px solid #dee2e6',
            borderRadius: 8,
          }}
        >
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}>
            <h3 style={{ margin: 0, fontSize: 14, color: '#666' }}>📋 결과</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                data-testid="copy-btn"
                onClick={() => navigator.clipboard.writeText(resultText)}
                style={{
                  padding: '6px 12px',
                  background: '#fff',
                  border: '1px solid #ccc',
                  borderRadius: 4,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                📋 복사
              </button>
              <button
                data-testid="result-close-btn"
                onClick={() => setResultText(null)}
                style={{
                  padding: '6px 12px',
                  background: 'transparent',
                  border: '1px solid #ccc',
                  borderRadius: 4,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                닫기
              </button>
            </div>
          </div>
          <div style={{
            whiteSpace: 'pre-wrap',
            lineHeight: 1.7,
            fontSize: 14,
            color: '#333',
          }}>
            {resultText}
          </div>
        </div>
      )}
    </div>
  );
}
