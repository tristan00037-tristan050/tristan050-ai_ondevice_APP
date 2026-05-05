import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

interface BotMessageProps {
  content: string | null;
  source?: 'factpack' | 'llm' | null;
  loadingStatus?: string;
  progressPercent?: number;
  streamBuffer?: string;
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

const mdComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  h1: ({ children }) => (
    <h1 style={{ fontSize: '1.5em', fontWeight: 700, margin: '0.75em 0 0.4em', color: 'var(--color-text-primary)', lineHeight: 1.3 }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: '1.25em', fontWeight: 700, margin: '0.75em 0 0.4em', color: 'var(--color-text-primary)', lineHeight: 1.3 }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: '1.1em', fontWeight: 600, margin: '0.6em 0 0.3em', color: 'var(--color-text-primary)', lineHeight: 1.3 }}>{children}</h3>
  ),
  p: ({ children }) => (
    <p style={{ margin: '0 0 0.75em', lineHeight: 1.7, color: 'var(--color-text-primary)' }}>{children}</p>
  ),
  strong: ({ children }) => (
    <strong style={{ fontWeight: 700, color: 'var(--color-text-primary)' }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ fontStyle: 'italic' }}>{children}</em>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '0.4em 0 0.75em', paddingLeft: '1.5em', listStyleType: 'disc' }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '0.4em 0 0.75em', paddingLeft: '1.5em', listStyleType: 'decimal' }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ margin: '0.25em 0', lineHeight: 1.65, color: 'var(--color-text-primary)' }}>{children}</li>
  ),
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '0.75em 0' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ padding: '6px 12px', border: '1px solid var(--color-border-subtle)', background: 'var(--color-bg-input)', fontWeight: 600, textAlign: 'left', color: 'var(--color-text-primary)' }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ padding: '6px 12px', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>{children}</td>
  ),
  code: ({ children, className }) => {
    const isBlock = Boolean(className);
    if (isBlock) {
      return (
        <code style={{ display: 'block', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.875em', color: 'var(--color-text-primary)' }}>{children}</code>
      );
    }
    return (
      <code style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.875em', background: 'var(--color-bg-input)', padding: '1px 5px', borderRadius: 4, color: 'var(--color-text-primary)' }}>{children}</code>
    );
  },
  pre: ({ children }) => (
    <pre style={{ margin: '0.5em 0 0.75em', padding: '12px 14px', background: 'var(--color-bg-input)', border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflowX: 'auto', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.875em', lineHeight: 1.5 }}>{children}</pre>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{ margin: '0.5em 0 0.75em', paddingLeft: '1em', borderLeft: '3px solid var(--color-brand-primary)', color: 'var(--color-text-secondary)' }}>{children}</blockquote>
  ),
  a: ({ children, href }) => {
    const safe = href && /^https?:\/\//.test(href) ? href : undefined;
    return (
      <a href={safe} target="_blank" rel="noreferrer noopener" style={{ color: 'var(--color-brand-primary)', textDecoration: 'underline' }}>{children}</a>
    );
  },
  hr: () => (
    <hr style={{ border: 'none', borderTop: '1px solid var(--color-border-subtle)', margin: '1em 0' }} />
  ),
};

function MarkdownContent({ text }: { text: string }) {
  return (
    <div data-testid="markdown-content" style={{ fontSize: 'var(--text-base)', lineHeight: 1.7 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={mdComponents}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

export function BotMessage({
  content,
  source,
  loadingStatus,
  progressPercent,
  streamBuffer,
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
          streamBuffer ? (
            <div data-testid="streaming-text">
              <MarkdownContent text={streamBuffer} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  color: 'var(--color-text-secondary)',
                  fontSize: 'var(--text-sm)',
                }}
              >
                <span data-testid="bot-loading-status">{loadingStatus ?? '생각 중'}</span>
                <ThinkingDots />
              </div>
              {progressPercent !== undefined && (
                <div
                  data-testid="bot-progress-bar-container"
                  style={{
                    height: 4,
                    borderRadius: 2,
                    background: 'var(--color-border-subtle)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    data-testid="bot-progress-bar"
                    style={{
                      height: '100%',
                      borderRadius: 2,
                      background: 'var(--color-brand-primary)',
                      width: `${Math.min(100, Math.max(0, progressPercent))}%`,
                      transition: 'width 300ms ease',
                    }}
                  />
                </div>
              )}
            </div>
          )
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
            <MarkdownContent text={content} />
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
