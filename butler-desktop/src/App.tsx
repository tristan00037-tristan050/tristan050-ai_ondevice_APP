import React, { useState, useRef } from 'react';
import { HomeScreen } from './components/HomeScreen';
import { EgressBadge } from './components/EgressBadge';
import { InputBar } from './components/InputBar';
import { ProgressOverlay } from './components/ProgressOverlay';
import type { SSEEvent } from './types';

export function App() {
  const [sseEvents, setSseEvents] = useState<SSEEvent[]>([]);
  const [overlayVisible, setOverlayVisible] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async (text: string, files: File[]) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setSseEvents([]);
    setOverlayVisible(true);

    try {
      const res = await fetch('/api/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text }),
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
      <HomeScreen />
      <InputBar onSubmit={handleSubmit} />
      <ProgressOverlay
        visible={overlayVisible}
        events={sseEvents}
        onCancel={handleCancel}
        onResult={() => setOverlayVisible(false)}
      />
    </div>
  );
}
