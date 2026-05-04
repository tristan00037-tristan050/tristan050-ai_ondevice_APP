import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ChatInput } from '../components/chat/ChatInput';

function makeFetchMock() {
  return vi.fn().mockImplementation((url: string | URL | Request) => {
    if (String(url).includes('/api/precheck')) {
      return Promise.resolve(
        new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      );
    }
    return Promise.resolve(new Response('{}', { status: 200 }));
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ChatInput', () => {
  it('test_happy_send_button_present_when_idle', () => {
    // processing=false → send-btn 표시
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );

    expect(screen.getByTestId('send-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('cancel-btn')).not.toBeInTheDocument();
  });

  it('test_happy_stop_button_when_processing', () => {
    // processing=true → cancel-btn 표시, text-input disabled
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={true}
        cardMode="free"
      />
    );

    expect(screen.getByTestId('cancel-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('send-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('text-input')).toBeDisabled();
  });

  it('test_happy_enter_submits', () => {
    // Enter 키 → onSubmit 호출
    const onSubmit = vi.fn();
    render(
      <ChatInput
        onSubmit={onSubmit}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );

    const textarea = screen.getByTestId('text-input');
    fireEvent.change(textarea, { target: { value: '테스트 메시지' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSubmit).toHaveBeenCalledWith('테스트 메시지', [], 'free');
  });

  it('test_boundary_shiftenter_newline', () => {
    // Shift+Enter → 줄바꿈 (전송 안 함)
    const onSubmit = vi.fn();
    render(
      <ChatInput
        onSubmit={onSubmit}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );

    const textarea = screen.getByTestId('text-input');
    fireEvent.change(textarea, { target: { value: '줄바꿈 테스트' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('test_happy_esc_stops_processing', () => {
    // Esc + processing → onStop 호출
    const onStop = vi.fn();
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={onStop}
        processing={true}
        cardMode="free"
      />
    );

    const textarea = screen.getByTestId('text-input');
    fireEvent.keyDown(textarea, { key: 'Escape' });

    expect(onStop).toHaveBeenCalled();
  });

  it('test_ux_processing_status_text_shown', () => {
    // processing=true → 처리 중 상태 텍스트 요소 표시 (WKWebView disabled placeholder 미표시 대응)
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={true}
        cardMode="free"
      />
    );
    expect(screen.getByTestId('processing-status-text')).toBeInTheDocument();
    expect(screen.getByTestId('processing-status-text').textContent).toBe('Butler가 답변을 준비하고 있습니다...');
  });

  it('test_ux_processing_status_text_hidden_when_idle', () => {
    // processing=false → 처리 중 상태 텍스트 숨김
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );
    expect(screen.queryByTestId('processing-status-text')).not.toBeInTheDocument();
  });

  it('test_ux_idle_placeholder_shown', () => {
    // processing=false → 기본 placeholder 표시
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );
    const textarea = screen.getByTestId('text-input') as HTMLTextAreaElement;
    expect(textarea.placeholder).toBe('무엇을 도와드릴까요? 자유롭게…');
  });

  it('test_ux_empty_submit_triggers_shake', () => {
    // 빈 입력에서 Enter → chat-input-wrapper에 shakeX 애니메이션 적용
    render(
      <ChatInput
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        processing={false}
        cardMode="free"
      />
    );
    const wrapper = screen.getByTestId('chat-input-wrapper');
    const textarea = screen.getByTestId('text-input');
    // textarea is empty; Enter triggers handleSubmit → triggerShake
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    expect(wrapper.style.animation).toContain('shakeX');
  });
});
