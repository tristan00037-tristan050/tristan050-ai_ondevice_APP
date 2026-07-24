import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DeleteConfirmModal } from '../components/chat/DeleteConfirmModal';


describe('DeleteConfirmModal accessibility contract', () => {
  it('exposes a labelled modal, moves focus, and closes on Escape', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const onCancel = vi.fn();
    render(<DeleteConfirmModal isOpen onConfirm={() => undefined} onCancel={onCancel} />);

    const dialog = screen.getByRole('dialog', { name: '대화 삭제' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    await new Promise(resolve => setTimeout(resolve, 1));
    expect(screen.getByTestId('delete-cancel-btn')).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    opener.remove();
  });
});
