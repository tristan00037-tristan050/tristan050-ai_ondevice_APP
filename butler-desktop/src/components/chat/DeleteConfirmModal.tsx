import React, { useRef } from 'react';
import { ModalFrame } from '../v1_1/ModalFrame';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmModal({ isOpen, onConfirm, onCancel }: DeleteConfirmModalProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  if (!isOpen) return null;

  return (
    <ModalFrame
      labelledBy="delete-confirm-title"
      testId="delete-confirm-modal"
      onClose={onCancel}
      initialFocusRef={cancelRef}
    >
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: 12,
          padding: '24px 28px',
          minWidth: 300,
          maxWidth: 400,
          boxShadow: '0 8px 32px rgba(0,0,0,0.16)',
        }}
      >
        <h3
          id="delete-confirm-title"
          style={{
            margin: '0 0 8px',
            fontSize: 'var(--text-lg)',
            color: 'var(--color-text-primary)',
          }}
        >
          대화 삭제
        </h3>
        <p
          style={{
            margin: '0 0 20px',
            fontSize: 'var(--text-sm)',
            color: 'var(--color-text-secondary)',
            lineHeight: 1.6,
          }}
        >
          대화를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button
            ref={cancelRef}
            data-testid="delete-cancel-btn"
            onClick={onCancel}
            style={{
              padding: '8px 16px',
              background: 'none',
              border: '1px solid var(--color-border-subtle)',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              color: 'var(--color-text-primary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            취소
          </button>
          <button
            data-testid="delete-confirm-btn"
            onClick={onConfirm}
            style={{
              padding: '8px 16px',
              background: 'var(--color-error)',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              color: '#FFFFFF',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
            }}
          >
            삭제
          </button>
        </div>
      </div>
    </ModalFrame>
  );
}
