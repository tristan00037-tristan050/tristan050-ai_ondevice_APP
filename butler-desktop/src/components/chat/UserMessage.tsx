import React from 'react';

interface UserMessageProps {
  content: string;
  timestamp: string;
}

export function UserMessage({ content, timestamp }: UserMessageProps) {
  const formattedTime = (() => {
    try {
      return new Date(timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return timestamp;
    }
  })();

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-end',
        marginBottom: 'var(--space-4)',
        animation: 'fadeInUp 200ms ease-out',
      }}
    >
      <div
        style={{
          maxWidth: '70%',
          background: 'var(--color-bg-message-user)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 12,
          padding: 'var(--space-3) var(--space-4)',
        }}
      >
        <div
          style={{
            fontSize: 'var(--text-base)',
            color: 'var(--color-text-primary)',
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
          }}
        >
          {content}
        </div>
        <div
          style={{
            marginTop: 'var(--space-1)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-secondary)',
            textAlign: 'right',
          }}
        >
          {formattedTime}
        </div>
      </div>
    </div>
  );
}
