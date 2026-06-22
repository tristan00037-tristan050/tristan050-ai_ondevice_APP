import React, { useState, useRef, useEffect } from 'react';
import { flushSync } from 'react-dom';
import { getVersion } from '@tauri-apps/api/app';
import { sidecarFetch, uiSafeSidecarErrorMessage } from './lib/sidecarFetch';
import butlerIconStaticUrl from './assets/butler-icon-static.svg';
import { EgressBadge } from './components/EgressBadge';
import { EgressMonitor } from './components/chat/EgressMonitor';
import { Sidebar } from './components/chat/Sidebar';
import { ChatInput } from './components/chat/ChatInput';
import { MessageList } from './components/chat/MessageList';
import { DeleteConfirmModal } from './components/chat/DeleteConfirmModal';
import { AccountingModal } from './components/chat/AccountingModal';
import { RequestParsingModal } from './components/chat/RequestParsingModal';
import { CardGrid } from './components/v1_1/CardGrid';
import { Card2DocumentTransform } from './components/v1_1/Card2DocumentTransform';
import { AdminPolicyConsole } from './components/v1_1/AdminPolicyConsole';
import { CompanyFormatConsole } from './components/v1_1/CompanyFormatConsole';
import { CompanyFactApprovalConsole } from './components/v1_1/CompanyFactApprovalConsole';
import { CompanyLearningConsole } from './components/v1_1/CompanyLearningConsole';
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
  streamBuffer: string;
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
  const [accountingModalOpen, setAccountingModalOpen] = useState(false);
  const [requestParsingModalOpen, setRequestParsingModalOpen] = useState(false);
  const [documentTransformModalOpen, setDocumentTransformModalOpen] = useState(false);
  const [adminPolicyConsoleOpen, setAdminPolicyConsoleOpen] = useState(false);
  const [companyFormatConsoleOpen, setCompanyFormatConsoleOpen] = useState(false);
  const [companyFactConsoleOpen, setCompanyFactConsoleOpen] = useState(false);
  const [companyLearningConsoleOpen, setCompanyLearningConsoleOpen] = useState(false);
  const [egressMonitorOpen, setEgressMonitorOpen] = useState(false);
  const [sidecarReady, setSidecarReady] = useState(false);
  const [sidecarElapsed, setSidecarElapsed] = useState(0);
  const [sidecarFailed, setSidecarFailed] = useState(false);
  // 헤더 버전 표시: 앱 버전(getVersion, 실패 시 빌드시 주입값으로 폴백), 엔진 버전(/health)
  const [appVersion, setAppVersion] = useState<string>(__APP_VERSION__);
  const [engineVersion, setEngineVersion] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    let isReady = false;
    const MAX_MS = 60_000;
    const FETCH_ABORT_MS = 1_500;
    const RETRY_MS = 500;
    const startMs = Date.now();

    const poll = async (): Promise<void> => {
      if (cancelled || isReady) return;
      setSidecarElapsed(Math.floor((Date.now() - startMs) / 1000));
      try {
        const ctrl = new AbortController();
        const abortHandle = setTimeout(() => ctrl.abort(), FETCH_ABORT_MS);
        const res = await fetch(`${SIDECAR_BASE}/health`, { signal: ctrl.signal });
        clearTimeout(abortHandle);
        if (!cancelled && res.ok) {
          isReady = true;
          setSidecarReady(true);
          // 엔진 버전 표시용. 파싱 실패해도 앱 흐름에는 영향 없음.
          try {
            const body = (await res.json()) as { version?: string };
            if (!cancelled && typeof body.version === 'string') {
              setEngineVersion(body.version);
            }
          } catch {
            // version 파싱 실패 — 헤더는 "엔진 –" 로 표시
          }
          return;
        }
      } catch {
        // sidecar not yet up — keep polling
      }
      if (!cancelled && !isReady && Date.now() - startMs < MAX_MS) {
        await new Promise<void>(r => setTimeout(r, RETRY_MS));
        return poll();
      } else if (!cancelled && !isReady) {
        setSidecarFailed(true);
      }
    };

    // Hard wall-clock guarantee: sidecarFailed set at exactly 60 s
    const failTimer = setTimeout(() => {
      if (!cancelled && !isReady) setSidecarFailed(true);
    }, MAX_MS);

    poll().finally(() => clearTimeout(failTimer));

    return () => {
      cancelled = true;
      clearTimeout(failTimer);
    };
  }, []);

  // 앱 버전: Tauri 런타임에서 getVersion() 조회. 비-Tauri(브라우저/테스트) 환경에서는
  // 실패하므로 빌드시 주입된 package.json version 폴백을 그대로 둔다.
  useEffect(() => {
    let cancelled = false;
    getVersion()
      .then(v => {
        if (!cancelled && v) setAppVersion(v);
      })
      .catch(() => {
        // 비-Tauri 환경 — __APP_VERSION__ 폴백 유지
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
      loadingStatus: '답변 준비중...',
      streamBuffer: '',
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

      // 비공개 sidecar 요청(POST /api/analyze/stream)에는 capability token 이 필요하다.
      // sidecarFetch 가 Authorization: Bearer <token> 을 자동 첨부한다(GET /health·/api/model/status 은
      // 토큰 불필요라 별도 fetch 유지). Content-Type 은 직접 지정하지 않는다 — FormData 가 multipart
      // boundary 까지 자동 설정하므로 건드리면 깨진다. token 미가용 시 fetch 전에 fail-closed 로 throw 되어
      // 아래 catch 에서 사용자 메시지로 처리된다(앱은 죽지 않음).
      const res = await sidecarFetch('/api/analyze/stream', {
        method: 'POST',
        body: formData,
        signal: ctrl.signal,
      });
      if (ctrl.signal.aborted) return;

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
        if (ctrl.signal.aborted) return;
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
          } else if (eventType === 'chunk') {
            const token = (data.token as string) ?? '';
            setPendingBot(prev => prev ? { ...prev, streamBuffer: prev.streamBuffer + token } : prev);
          } else if (eventType === 'phase_start') {
            const msg = (data.status_message as string) || '분석 중';
            // flushSync forces React DOM update; sidecar heartbeats keep the connection alive
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 5 } : prev);
            });
          } else if (eventType === 'chunk_progress') {
            const current = (data.current as number) ?? 0;
            const total = (data.total as number) ?? 1;
            const msg = (data.status_message as string) || `처리 중 (${current}/${total})`;
            // 5–70%: monotonic scale avoids backward jump when reduce_start follows at fixed 85%
            const pct = 5 + Math.round((current / total) * 65);
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: pct } : prev);
            });
          } else if (eventType === 'reduce_start') {
            const msg = (data.status_message as string) || '정리 중';
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 85 } : prev);
            });
          } else if (eventType === 'verify_start') {
            const msg = (data.status_message as string) || '확인 중';
            flushSync(() => {
              setPendingBot(prev => prev ? { ...prev, loadingStatus: msg, progressPercent: 95 } : prev);
            });
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
              ? { ...prev, content: cancelMsg, isError: true, loadingStatus: '', streamBuffer: '' }
              : prev
            );
            setProcessing(false);
            return;
          } else if (eventType === 'error') {
            const errMsg = (data.message as string) ?? '알 수 없는 오류가 발생했습니다.';
            setPendingBot(prev => prev
              ? { ...prev, content: errMsg, isError: true, loadingStatus: '', streamBuffer: '' }
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
        // token 미가용(CAPABILITY_TOKEN_EMPTY)·연결 실패 등을 토큰/원문 노출 없이 사용자 메시지로 변환.
        setPendingBot(prev => prev
          ? { ...prev, content: uiSafeSidecarErrorMessage(err), isError: true, loadingStatus: '', streamBuffer: '' }
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
    const m = mode ?? 'free';
    setCardMode(m);
    if (m === 'accounting_classify') {
      setAccountingModalOpen(true);
    } else if (m === 'request_organize') {
      setRequestParsingModalOpen(true);
    } else if (m === 'format_convert') {
      setDocumentTransformModalOpen(true);
    }
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <img
              src={butlerIconStaticUrl}
              width={24}
              height={24}
              alt=""
              data-testid="butler-header-icon"
            />
            <span
              style={{
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                color: 'var(--color-brand-primary)',
              }}
            >
              Butler
            </span>
            <span
              data-testid="app-version-info"
              title="앱 버전 · 빌드(브랜치 커밋) · 엔진 버전"
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
                opacity: 0.7,
                whiteSpace: 'nowrap',
              }}
            >
              v{appVersion} · {__BUILD_BRANCH__} {__BUILD_COMMIT__} · 엔진 {engineVersion ?? '–'}
            </span>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <button
              data-testid="admin-policy-console-btn"
              onClick={() => setAdminPolicyConsoleOpen(true)}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              정책 등록
            </button>
            <button
              data-testid="company-format-console-btn"
              onClick={() => setCompanyFormatConsoleOpen(true)}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              양식 등록
            </button>
            <button
              data-testid="company-fact-console-btn"
              onClick={() => setCompanyFactConsoleOpen(true)}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              회사 지식 승인
            </button>
            <button
              data-testid="company-learning-console-btn"
              onClick={() => setCompanyLearningConsoleOpen(true)}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              폴더 학습 후보
            </button>
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
          </div>
        </div>

        {/* Content area — card grid always visible; compact strip when messages present */}
        {hasMessages ? (
          <>
            <CardGrid onCardSelect={handleCardSelect} />
            <MessageList
              messages={activeConv?.messages ?? []}
              pendingBot={pendingBot}
              onRetry={() => {
                setPendingBot(null);
              }}
            />
          </>
        ) : (
          <CardGrid onCardSelect={handleCardSelect} />
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

      {accountingModalOpen && (
        <AccountingModal
          onClose={() => {
            setAccountingModalOpen(false);
            setCardMode('free');
          }}
        />
      )}

      {requestParsingModalOpen && (
        <RequestParsingModal
          onClose={() => {
            setRequestParsingModalOpen(false);
            setCardMode('free');
          }}
        />
      )}

      {documentTransformModalOpen && (
        <Card2DocumentTransform
          onClose={() => {
            setDocumentTransformModalOpen(false);
            setCardMode('free');
          }}
        />
      )}
      {adminPolicyConsoleOpen && (
        <AdminPolicyConsole onClose={() => setAdminPolicyConsoleOpen(false)} />
      )}
      {companyFormatConsoleOpen && (
        <CompanyFormatConsole onClose={() => setCompanyFormatConsoleOpen(false)} />
      )}
      {companyFactConsoleOpen && (
        <CompanyFactApprovalConsole onClose={() => setCompanyFactConsoleOpen(false)} />
      )}
      {companyLearningConsoleOpen && (
        <CompanyLearningConsole onClose={() => setCompanyLearningConsoleOpen(false)} />
      )}
      {/* Sidecar readiness overlay */}
      {!sidecarReady && !sidecarFailed && (
        <div
          data-testid="sidecar-loading"
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--color-bg-app)',
          }}
        >
          <div style={{ textAlign: 'center', padding: '40px 32px' }}>
            <p style={{ fontSize: 40, margin: '0 0 16px' }}>⚙️</p>
            <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>분석 엔진 시작 중</h2>
            <p data-testid="sidecar-elapsed" style={{ color: 'var(--color-text-secondary)', fontSize: 14, margin: 0 }}>
              {sidecarElapsed}초 경과 / 최대 60초
            </p>
          </div>
        </div>
      )}
      {!sidecarReady && sidecarFailed && (
        <div
          data-testid="sidecar-failed"
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--color-bg-app)',
          }}
        >
          <div style={{ textAlign: 'center', padding: '40px 32px', maxWidth: 400 }}>
            <p style={{ fontSize: 32, margin: '0 0 16px' }}>⚠️</p>
            <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>분석 엔진 연결 실패</h2>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: 14, margin: 0 }}>
              60초 동안 응답이 없습니다. Butler.app을 재실행해주세요.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
