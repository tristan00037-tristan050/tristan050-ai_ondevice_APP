import React, { useState } from 'react';

interface BotMessageProps {
  content: string | null;
  source?: 'factpack' | 'llm' | null;
  loadingStatus?: string;
  factId?: string;
  score?: number;
  isError?: boolean;
  onRetry?: () => void;
  isLast?: boolean;
}

function SourceBadge({ source }: { source?: 'factpack' | 'llm' | null }) {
  if (!source) return null;

  if (source === 'factpack') {
    return (
      <span
        style={{
          fontSize: 'var(--text-xs)',
          padding: '2px 8px',
          borderRadius: 99,
          background: 'rgba(15,123,15,0.1)',
          color: 'var(--color-success)',
          fontWeight: 500,
        }}
      >
        ✓ 검증된 사실
      </span>
    );
  }

  return (
    <span
      style={{
        fontSize: 'var(--text-xs)',
        padding: '2px 8px',
        borderRadius: 99,
        background: 'rgba(16,54,125,0.1)',
        color: 'var(--color-brand-primary)',
        fontWeight: 500,
      }}
    >
      ✨ AI 생성
    </span>
  );
}

function ThinkingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--color-brand-primary)',
            display: 'inline-block',
            animation: `thinkDot 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

export function BotMessage({
  content,
  source,
  loadingStatus,
  isError = false,
  onRetry,
  isLast = false,
}: BotMessageProps) {
  const [showCopy, setShowCopy] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div
      data-testid={isLast ? 'result-panel' : undefined}
      style={{
        display: 'flex',
        flexDirection: 'column',
        marginBottom: 'var(--space-4)',
        animation: 'fadeInUp 200ms ease-out',
      }}
      onMouseEnter={() => setShowCopy(true)}
      onMouseLeave={() => setShowCopy(false)}
    >
      {/* Header: avatar + name + badge */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          marginBottom: 'var(--space-2)',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: 'var(--color-brand-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFFFFF',
            fontSize: 14,
            flexShrink: 0,
          }}
        >
          🤖
        </div>
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
          }}
        >
          Butler
        </span>
        <SourceBadge source={source} />
      </div>

      {/* Body */}
      <div style={{ paddingLeft: 36 }}>
        {content === null ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              color: 'var(--color-text-secondary)',
              fontSize: 'var(--text-sm)',
            }}
          >
            <span>{loadingStatus ?? '생각 중'}</span>
            <ThinkingDots />
          </div>
        ) : isError ? (
          <div>
            <p
              style={{
                color: 'var(--color-error)',
                fontSize: 'var(--text-sm)',
                margin: 0,
                whiteSpace: 'pre-wrap',
              }}
            >
              {content}
            </p>
            {onRetry && (
              <button
                onClick={onRetry}
                style={{
                  marginTop: 'var(--space-2)',
                  padding: '4px 12px',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-brand-primary)',
                  background: 'none',
                  border: '1px solid var(--color-brand-primary)',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                다시 시도
              </button>
            )}
          </div>
        ) : (
          <div>
            <div
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--color-text-primary)',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.7,
              }}
            >
              {content}
            </div>
            {content && (
              <button
                data-testid="copy-btn"
                onClick={handleCopy}
                style={{
                  marginTop: 'var(--space-2)',
                  padding: '4px 10px',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-text-secondary)',
                  background: 'var(--color-bg-input)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 6,
                  cursor: 'pointer',
                  opacity: showCopy || copied ? 1 : 0,
                  transition: 'opacity 150ms ease',
                  pointerEvents: showCopy || copied ? 'auto' : 'none',
                }}
              >
                {copied ? '✓ 복사됨' : '📋 복사'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
