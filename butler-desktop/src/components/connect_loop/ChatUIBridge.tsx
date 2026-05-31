import React, { useState } from 'react';
import type { ChatBridgeResult } from '../../lib/connect_loop/client';
import { runChatBridge } from '../../lib/connect_loop/client';
import { SecurityBadges } from './SecurityBadges';

interface BridgeMessage {
  id: string;
  role: 'user' | 'butler';
  text: string;
  result?: ChatBridgeResult;
}

interface ChatUIBridgeProps {
  runBridge?: (text: string) => Promise<ChatBridgeResult>;
}

function messageId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ChatUIBridge({ runBridge = runChatBridge }: ChatUIBridgeProps) {
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<BridgeMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [lastResult, setLastResult] = useState<ChatBridgeResult | null>(null);

  const handleSubmit = async () => {
    let runtimeText: string | null = inputValue.trim();
    if (!runtimeText || pending) return;

    const userMessage: BridgeMessage = {
      id: messageId('user'),
      role: 'user',
      text: runtimeText,
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setPending(true);

    try {
      const result = await runBridge(runtimeText);
      const butlerMessage: BridgeMessage = {
        id: messageId('butler'),
        role: 'butler',
        text: result.displayText,
        result,
      };
      setLastResult(result);
      setMessages(prev => [...prev, butlerMessage]);
    } catch {
      const result: ChatBridgeResult = {
        status: 'endpoint_failed',
        displayText: '실행에 실패했습니다. 다시 시도하거나 문의해 주세요.',
        chatRequest: {
          request_id: 'unavailable',
          session_id_digest: `sha256:${'0'.repeat(64)}`,
          tenant_id_digest: `sha256:${'0'.repeat(64)}`,
          device_id: 'butler-desktop-device',
          user_role: 'employee',
          department_id_digest: `sha256:${'0'.repeat(64)}`,
          text_ref: 'device_local_only',
          text_digest: `sha256:${'0'.repeat(64)}`,
          attachments: [],
          created_at: '2026-05-30T00:00:00Z',
          schema_version: 'chat_request.v1',
        },
        decision: null,
        boxResponse: null,
        requestId: 'unavailable',
        usageLogCount: null,
        usageLogVerification: 'not_configured',
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
      setLastResult(result);
      setMessages(prev => [...prev, { id: messageId('butler'), role: 'butler', text: result.displayText, result }]);
    } finally {
      runtimeText = null;
      setPending(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <section
      aria-label="Connect Loop Chat UI Bridge"
      data-testid="connect-loop-chat-ui-bridge"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        minHeight: 520,
        padding: 20,
        background: 'var(--color-bg-app)',
        color: 'var(--color-text-primary)',
      }}
    >
      <header>
        <h2 style={{ margin: '0 0 6px', fontSize: 22 }}>연결 루프 채팅</h2>
        <p style={{ margin: 0, color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
          입력은 로컬 라우터에서 의도 판정 후 허용된 박스만 실행합니다.
        </p>
      </header>

      <div
        data-testid="connect-loop-message-list"
        style={{
          flex: 1,
          overflowY: 'auto',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 8,
          padding: 14,
          background: 'var(--color-bg-input)',
        }}
      >
        {messages.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--color-text-secondary)' }}>
            요청을 입력하면 PR-C 라우터 결정과 보안 배지가 함께 표시됩니다.
          </p>
        ) : (
          messages.map(message => (
            <article
              key={message.id}
              data-testid={`connect-loop-message-${message.role}`}
              style={{
                marginBottom: 14,
                padding: 12,
                borderRadius: 8,
                background: message.role === 'user' ? '#F5F7FA' : '#FFFFFF',
                border: '1px solid var(--color-border-subtle)',
              }}
            >
              <strong style={{ display: 'block', marginBottom: 6 }}>
                {message.role === 'user' ? '사용자' : 'Butler'}
              </strong>
              <p style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.55 }}>{message.text}</p>
              {message.result && (
                <SecurityBadges
                  decision={message.result.decision}
                  fallbackRequired={message.result.decision?.fallback_required ?? message.result.status !== 'executed'}
                  integrationMode={message.result.integrationMode}
                  usageLogCount={message.result.usageLogCount}
                  usageLogVerification={message.result.usageLogVerification}
                />
              )}
            </article>
          ))
        )}
      </div>

      {lastResult?.decision && (
        <aside
          data-testid="connect-loop-router-decision"
          style={{
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 8,
            padding: 12,
            fontSize: 'var(--text-sm)',
            color: 'var(--color-text-secondary)',
          }}
        >
          <div>intent: {lastResult.decision.intent_label}</div>
          <div>endpoint: {lastResult.decision.target_endpoint}</div>
          <div>reason: {lastResult.decision.reason_code}</div>
        </aside>
      )}

      <div
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'flex-end',
        }}
      >
        <textarea
          data-testid="connect-loop-input"
          value={inputValue}
          onChange={event => setInputValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="요청을 입력하세요"
          rows={3}
          disabled={pending}
          style={{
            flex: 1,
            resize: 'vertical',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 8,
            padding: 12,
            fontSize: 'var(--text-base)',
            fontFamily: 'var(--font-sans)',
            lineHeight: 1.5,
          }}
        />
        <button
          data-testid="connect-loop-send"
          type="button"
          onClick={handleSubmit}
          disabled={pending || !inputValue.trim()}
          style={{
            minWidth: 92,
            height: 44,
            border: 'none',
            borderRadius: 8,
            background: pending || !inputValue.trim() ? '#A8ADB7' : 'var(--color-brand-primary)',
            color: '#FFFFFF',
            cursor: pending || !inputValue.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          {pending ? '처리 중' : '전송'}
        </button>
      </div>
    </section>
  );
}
