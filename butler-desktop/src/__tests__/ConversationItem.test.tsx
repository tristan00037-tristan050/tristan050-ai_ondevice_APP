import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationItem } from '../components/chat/ConversationItem';
import type { Conversation } from '../types';

function makeConv(overrides?: Partial<Conversation>): Conversation {
  return {
    id: 'test-conv-1',
    title: '테스트 대화',
    title_is_custom: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [],
    ...overrides,
  };
}

describe('ConversationItem', () => {
  it('test_happy_rename_enter_saves', async () => {
    // Enter 키 → onRename 호출
    const onRename = vi.fn();
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );

    // Enter edit mode via double-click
    fireEvent.dblClick(screen.getByText('테스트 대화'));
    const input = screen.getByTestId('conv-rename-input');
    fireEvent.change(input, { target: { value: '새 이름' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onRename).toHaveBeenCalledWith('새 이름');
  });

  it('test_happy_rename_esc_cancels', () => {
    // Esc 키 → 취소 (onRename 미호출)
    const onRename = vi.fn();
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );

    fireEvent.dblClick(screen.getByText('테스트 대화'));
    const input = screen.getByTestId('conv-rename-input');
    fireEvent.change(input, { target: { value: '취소될 이름' } });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(onRename).not.toHaveBeenCalled();
    // Edit mode exits — input should be gone
    expect(screen.queryByTestId('conv-rename-input')).not.toBeInTheDocument();
  });

  it('test_boundary_empty_string_rejected', () => {
    // 빈 문자열 입력 → onRename 미호출
    const onRename = vi.fn();
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );

    fireEvent.dblClick(screen.getByText('테스트 대화'));
    const input = screen.getByTestId('conv-rename-input');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onRename).not.toHaveBeenCalled();
  });

  it('test_happy_doubleclick_enters_edit_mode', () => {
    // 더블클릭 → rename input 표시
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.queryByTestId('conv-rename-input')).not.toBeInTheDocument();
    fireEvent.dblClick(screen.getByText('테스트 대화'));
    expect(screen.getByTestId('conv-rename-input')).toBeInTheDocument();
  });

  it('test_happy_rename_blur_saves', () => {
    // blur → 자동 저장 (onRename 호출)
    const onRename = vi.fn();
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );

    fireEvent.dblClick(screen.getByText('테스트 대화'));
    const input = screen.getByTestId('conv-rename-input');
    fireEvent.change(input, { target: { value: 'blur로 저장' } });
    fireEvent.blur(input);

    expect(onRename).toHaveBeenCalledWith('blur로 저장');
  });

  it('test_boundary_whitespace_only_rejected', () => {
    // 공백만 입력 → onRename 미호출
    const onRename = vi.fn();
    const conv = makeConv();
    render(
      <ConversationItem
        conversation={conv}
        isActive={false}
        onSelect={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );

    fireEvent.dblClick(screen.getByText('테스트 대화'));
    const input = screen.getByTestId('conv-rename-input');
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onRename).not.toHaveBeenCalled();
  });
});
