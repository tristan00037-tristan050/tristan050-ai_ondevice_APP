import React, { useState, useRef } from 'react';
import { flushSync } from 'react-dom';
import { EgressBadge } from './components/EgressBadge';
import { EgressMonitor } from './components/chat/EgressMonitor';
import { Sidebar } from './components/chat/Sidebar';
import { EmptyState } from './components/chat/EmptyState';
import { ChatInput } from './components/chat/ChatInput';
import { MessageList } from './components/chat/MessageList';
import { DeleteConfirmModal } from './components/chat/DeleteConfirmModal';
import { SIDECAR_BASE } from './constants';
import type { SSEEvent, Conversation, Message } from './types';
import {
  loadConversations,
  saveConversations,
  upsertConversation,
  deleteConversation,
  generateId,
} from './lib/storage';

type PendingBotState = {
  source: 'factpack' | 'llm' | null;
  loadingStatus: string;
  progressPercent?: number;
  content: string | null;
  isError: boolean;
  factId?: string;
  score?: number;
};

const CARD_MODE_MAP: Record<number, string> = {
  1: 'request_organize',
  2: 'format_convert',
  3: 'new_draft',
  4: 'attachment_edit',
  5: 'accounting_classify',
  6: 'form_fill',
};

// Suppress unused import warning — CARD_MODE_MAP used below
void CARD_MODE_MAP;

export function App() {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [pendingBot, setPendingBot] = useState<PendingBotState | null>(null);
  const [processing, setProcessing] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [cardMode, setCardMode] = useState<string>('free');
  const [egressMonitorOpen, setEgressMonitorOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const activeConv = conversations.find(c => c.id === activeConvId) ?? null;
  const hasMessages = (activeConv?.messages.length ?? 0) > 0 || pendingBot !== null;

  // --- Conversation management ---

  const createNewConversation = (): Conversation => {
    const now = new Date().toISOString();
    return {
      id: generateId(),
      title: '새 대화',
      title_is_custom: false,
      created_at: now,
      updated_at: now,
      messages: [],
    };
  };

  const handleNewConv = () => {
    setActiveConvId(null);
    setPendingBot(null);
    setCardMode('free');
    if (processing) {
      abortRef.current?.abort();
      setProcessing(false);
    }
  };

  const handleSelectConv = (id: string) => {
    if (processing) {
      abortRef.current?.abort();
      setProcessing(false);
    }
    setPendingBot(null);
    setActiveConvId(id);
  };

  const handleRename = (id: string, title: string) => {
    setConversations(prev => {
      const updated = prev.map(c =>
        c.id === id ? { ...c, title, title_is_custom: true } : c
      );
      saveConversations(updated);
      return updated;
    });
  };

  const handleDeleteRequest = (id: string) => {
    setDeleteTarget(id);
  };

  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    deleteConversation(deleteTarget);
    setConversations(prev => prev.filter(c => c.id !== deleteTarget));
    if (activeConvId === deleteTarget) {
      setActiveConvId(null);
      setPendingBot(null);
    }
    setDeleteTarget(null);
  };

  const handleDeleteCancel = () => {
    setDeleteTarget(null);
  };

  // --- Submit handler ---

  const handleSubmit = async (text: string, files: File[], mode: string) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let currentSource: 'factpack' | 'llm' | null = null;

    // Get or create conversation
    let conv: Conversation;
    if (activeConvId) {
      conv = conversations.find(c => c.id === activeConvId) ?? createNewConversation();
    } else {
      conv = createNewConversation();
    }

    const now = new Date().toISOString();

    // User message
    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: now,
    };

    // Update title from first message if not custom
    const isFirstMessage = conv.messages.length === 0;
    const newTitle = isFirstMessage && !conv.title_is_custom
      ? text.slice(0, 40) || '새 대화'
      : conv.title;

    const updatedConv: Conversation = {
      ...conv,
      title: newTitle,
      updated_at: now,
      messages: [...conv.messages, userMsg],
    };

    // Update state
    setConversations(prev => {
      const idx = prev.findIndex(c => c.id === updatedConv.id);
      let next: Conversation[];
      if (idx >= 0) {
        next = prev.map(c => (c.id === updatedConv.id ? updatedConv : c));
      } else {
        next = [updatedConv, ...prev];
      }
      saveConversations(next);
      return next;
    });
    setActiveConvId(updatedConv.id);

    // Start pending bot
    setPendingBot({
      source: null,
      loadingStatus: '생각 중',
      content: null,
      isError: false,
    });
    setProcessing(true);

    try {
      const formData = new FormData();
      formData.append('query', text);
      formData.append('card_mode', mode || 'free');
      formData.append('total_chunks', '1');
      files.forEach((file, idx) => formData.append(`file_${idx}`, file));
      formData.append('file_count', String(files.length));

      const res = await fetch(`${SIDECAR_BASE}/api/analyze/stream`, {
        method: 'POST',
        body: formData,
        signal: ctrl.signal,
      });

      const reader = res.body?.getReader();
      if (!reader) {
        setPendingBot(null);
        setProcessing(false);
        return;
      }

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
          if (!dataLine) continue;

          const eventType = (eventLine?.slice(6).trim() ?? 'unknown') as SSEEvent['type'];
          let data: Record<string, unknown> = {};
          try {
            data = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>;
          } catch {
            continue;
          }

          if (eventType === 'meta') {
            const src = data.source as 'factpack' | 'llm' | undefined;
            currentSource = src ?? null;
            setPendingBot(prev => prev ? { ...prev, source: src ?? null } : prev);
          } else if (eventType === 'phase_start') {
            const msg = (data.status_message as string) || '분석 중';
            // flushSync forces React DOM update; setTimeout(0) yields to browser paint cycle
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 5 } : prev);
            });
            await new Promise<void>(r => setTimeout(r, 0));
          } else if (eventType === 'chunk_progress') {
            const current = (data.current as number) ?? 0;
            const total = (data.total as number) ?? 1;
            const msg = (data.status_message as string) || `처리 중 (${current}/${total})`;
            // 5–70%: monotonic scale avoids backward jump when reduce_start follows at fixed 85%
            const pct = 5 + Math.round((current / total) * 65);
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: pct } : prev);
            });
            await new Promise<void>(r => setTimeout(r, 0));
          } else if (eventType === 'reduce_start') {
            const msg = (data.status_message as string) || '정리 중';
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 85 } : prev);
            });
            await new Promise<void>(r => setTimeout(r, 0));
          } else if (eventType === 'verify_start') {
            const msg = (data.status_message as string) || '확인 중';
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 95 } : prev);
            });
            await new Promise<void>(r => setTimeout(r, 0));
          } else if (eventType === 'complete') {
            const resultText = (data.result_text as string) ?? '';
            const botMsg: Message = {
              id: generateId(),
              role: 'butler',
              content: resultText,
              timestamp: new Date().toISOString(),
              source: currentSource ?? undefined,
            };

            setConversations(prev => {
              const updated = prev.map(c => {
                if (c.id !== updatedConv.id) return c;
                return {
                  ...c,
                  updated_at: new Date().toISOString(),
                  messages: [...c.messages, botMsg],
                };
              });
              saveConversations(updated);
              return updated;
            });

            // Clear pendingBot — the result is now in conversations
            setPendingBot(null);
            setProcessing(false);
            return;
          } else if (eventType === 'cancelled') {
            const reason = (data.reason as string) ?? 'user_cancel';
            const cancelMsg =
              reason === 'chunk_timeout'
                ? '한 청크가 너무 오래 걸려 중단됐습니다.'
                : reason === 'hard_timeout'
                ? '전체 시간 초과 (300초)로 중단됐습니다.'
                : '작업이 중단됐습니다.';
            setPendingBot(prev => prev
              ? { ...prev, content: cancelMsg, isError: true, loadingStatus: '' }
              : prev
            );
            setProcessing(false);
            return;
          } else if (eventType === 'error') {
            const errMsg = (data.message as string) ?? '알 수 없는 오류가 발생했습니다.';
            setPendingBot(prev => prev
              ? { ...prev, content: errMsg, isError: true, loadingStatus: '' }
              : prev
            );
            setProcessing(false);
            return;
          }
        }
      }
    } catch (err: unknown) {
      const isAbort = err instanceof Error && err.name === 'AbortError';
      if (!isAbort) {
        setPendingBot(prev => prev
          ? { ...prev, content: '요청 중 오류가 발생했습니다.', isError: true, loadingStatus: '' }
          : prev
        );
      } else {
        setPendingBot(null);
      }
      setProcessing(false);
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setProcessing(false);
    setPendingBot(null);
  };

  const handleCardSelect = (mode: string | null) => {
    setCardMode(mode ?? 'free');
  };

  return (
    <div style={{ display: 'flex', height: '100%', background: 'var(--color-bg-app)' }}>
      <Sidebar
        conversations={conversations}
        activeConvId={activeConvId}
        onSelect={handleSelectConv}
        onNew={handleNewConv}
        onRename={handleRename}
        onDeleteRequest={handleDeleteRequest}
        isOpen={sidebarOpen}
      />

      <main
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minWidth: 0,
        }}
      >
        {/* Top bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: 'var(--space-3) var(--space-4)',
            borderBottom: '1px solid var(--color-border-subtle)',
            background: 'var(--color-bg-input)',
            gap: 'var(--space-3)',
          }}
        >
          <button
            data-testid="sidebar-toggle-btn"
            onClick={() => setSidebarOpen(o => !o)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 18,
              color: 'var(--color-text-secondary)',
              padding: '2px 4px',
              borderRadius: 4,
            }}
            aria-label="사이드바 토글"
          >
            ☰
          </button>
          <span
            style={{
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              color: 'var(--color-brand-primary)',
            }}
          >
            Butler
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <button
              data-testid="egress-monitor-btn"
              onClick={() => setEgressMonitorOpen(true)}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
              aria-label="Egress Monitor 열기"
            >
              🔒 외부 송신 0
            </button>
            <EgressBadge />
          </div>
        </div>

        {/* Content area */}
        {hasMessages ? (
          <MessageList
            messages={activeConv?.messages ?? []}
            pendingBot={pendingBot}
            onRetry={() => {
              // Clear error state for retry
              setPendingBot(null);
            }}
          />
        ) : (
          <EmptyState onCardSelect={handleCardSelect} />
        )}

        <ChatInput
          onSubmit={handleSubmit}
          onStop={handleStop}
          processing={processing}
          cardMode={cardMode}
        />
      </main>

      {deleteTarget && (
        <DeleteConfirmModal
          isOpen={true}
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
        />
      )}

      {egressMonitorOpen && (
        <EgressMonitor onClose={() => setEgressMonitorOpen(false)} />
      )}
    </div>
  );
}
