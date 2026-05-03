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
});
