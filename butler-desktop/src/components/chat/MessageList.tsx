import React, { useEffect, useRef } from 'react';
import type { Message } from '../../types';
import { UserMessage } from './UserMessage';
import { BotMessage } from './BotMessage';

interface PendingBotState {
  source?: 'factpack' | 'llm' | null;
  loadingStatus: string;
  progressPercent?: number;
  streamBuffer?: string;
  content: string | null;
  isError?: boolean;
}

interface MessageListProps {
  messages: Message[];
  pendingBot?: PendingBotState | null;
  onRetry?: () => void;
}

export function MessageList({ messages, pendingBot, onRetry }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bottomRef.current && typeof bottomRef.current.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, pendingBot]);

  // Find index of the last butler message (for result-panel testid)
  const lastButlerIdx = !pendingBot
    ? [...messages].map((m, i) => ({ role: m.role, i })).filter(x => x.role === 'butler').at(-1)?.i ?? -1
    : -1;

  return (
    <div
      data-testid="message-list"
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-6) var(--space-4)',
      }}
    >
      <div
        style={{
          maxWidth: 760,
          margin: '0 auto',
        }}
      >
        {messages.map((msg, idx) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} data-testid={`user-message-${idx}`}>
                <UserMessage content={msg.content} timestamp={msg.timestamp} />
              </div>
            );
          }
          const isLast = idx === lastButlerIdx;
          return (
            <div key={msg.id} data-testid={`bot-message-${idx}`}>
              <BotMessage
                content={msg.content}
                source={msg.source}
                isLast={isLast}
                onRetry={onRetry}
              />
            </div>
          );
        })}

        {pendingBot && (
          <div data-testid={`bot-message-${messages.length}`}>
            <BotMessage
              content={pendingBot.content}
              source={pendingBot.source ?? undefined}
              loadingStatus={pendingBot.loadingStatus}
              progressPercent={pendingBot.progressPercent}
              streamBuffer={pendingBot.streamBuffer}
              isError={pendingBot.isError}
              isLast={true}
              onRetry={onRetry}
            />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
