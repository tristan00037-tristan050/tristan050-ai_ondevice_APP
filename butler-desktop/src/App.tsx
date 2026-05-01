import React, { useState, useRef } from 'react';
import { HomeScreen } from './components/HomeScreen';
import { EgressBadge } from './components/EgressBadge';
import { InputBar } from './components/InputBar';
import { ProgressOverlay } from './components/ProgressOverlay';
import type { SSEEvent } from './types';

export function App() {
  const [sseEvents, setSseEvents] = useState<SSEEvent[]>([]);
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [cardMode, setCardMode] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async (text: string, files: File[]) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setSseEvents([]);
    setOverlayVisible(true);

    try {
      const formData = new FormData();
      formData.append('query', text);
      formData.append('card_mode', String(cardMode ?? 'free'));
      formData.append('total_chunks', '1');
      files.forEach((file, idx) => formData.append(`file_${idx}`, file));
      formData.append('file_count', String(files.length));

      const res = await fetch('/api/analyze/stream', {
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
        const lines = buf.split('\n\n');
        buf = lines.pop() ?? '';
        for (const block of lines) {
          const dataLine = block.split('\n').find(l => l.startsWith('data:'));
          if (dataLine) {
            const evt = JSON.parse(dataLine.slice(5).trim()) as SSEEvent;
            setSseEvents(prev => [...prev, evt]);
          }
        }
      }
    } catch {
      // aborted or error — ProgressOverlay handles via events
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
      <HomeScreen onCardSelect={setCardMode}>
        <InputBar onSubmit={handleSubmit} />
      </HomeScreen>
      <ProgressOverlay
        visible={overlayVisible}
        events={sseEvents}
        onCancel={handleCancel}
        onResult={() => setOverlayVisible(false)}
      />
    </div>
  );
}
