import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageList } from '../components/chat/MessageList';
import type { Message } from '../types';

function makeMessage(overrides: Partial<Message> & { id: string; role: 'user' | 'butler'; content: string }): Message {
  return {
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe('MessageList', () => {
  it('test_happy_renders_messages', () => {
    // 메시지 3개 전달 시 3개 렌더
    const messages: Message[] = [
      makeMessage({ id: '1', role: 'user', content: '안녕하세요' }),
      makeMessage({ id: '2', role: 'butler', content: '안녕하세요! 무엇을 도와드릴까요?' }),
      makeMessage({ id: '3', role: 'user', content: '요청사항입니다' }),
    ];

    render(<MessageList messages={messages} />);

    expect(screen.getByTestId('user-message-0')).toBeInTheDocument();
    expect(screen.getByTestId('bot-message-1')).toBeInTheDocument();
    expect(screen.getByTestId('user-message-2')).toBeInTheDocument();
  });

  it('test_happy_user_message_right_aligned', () => {
    // user 메시지 right-aligned
    const messages: Message[] = [
      makeMessage({ id: '1', role: 'user', content: '사용자 메시지' }),
    ];

    render(<MessageList messages={messages} />);

    const wrapper = screen.getByTestId('user-message-0');
    // The UserMessage component renders a flex container with justify-content: flex-end
    // Check the inner element has the correct style
    const flexContainer = wrapper.firstElementChild as HTMLElement;
    expect(flexContainer).not.toBeNull();
    expect(flexContainer.style.justifyContent).toBe('flex-end');
  });

  it('test_happy_pending_bot_shows_loading', () => {
    // pendingBot.content=null → 로딩 상태 표시
    const messages: Message[] = [
      makeMessage({ id: '1', role: 'user', content: '질문' }),
    ];

    render(
      <MessageList
        messages={messages}
        pendingBot={{
          source: null,
          loadingStatus: '생각 중',
          content: null,
          isError: false,
        }}
      />
    );

    // The pending bot message should be rendered
    expect(screen.getByTestId(`bot-message-${messages.length}`)).toBeInTheDocument();
    // Loading status text should be visible
    expect(screen.getByText('생각 중')).toBeInTheDocument();
  });
});
