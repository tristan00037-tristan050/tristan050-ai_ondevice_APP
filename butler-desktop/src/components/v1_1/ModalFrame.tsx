import React, { useEffect, useRef, type ReactNode, type RefObject } from 'react';

type Props = {
  labelledBy: string;
  testId: string;
  onClose: () => void;
  initialFocusRef: RefObject<HTMLElement>;
  children: ReactNode;
};

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    element => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true'
  );
}

export function ModalFrame({ labelledBy, testId, onClose, initialFocusRef, children }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const dialog = dialogRef.current;
    document.body.style.overflow = 'hidden';

    const inertedSiblings: Array<{ element: HTMLElement; inert: string | null; ariaHidden: string | null }> = [];
    const parent = dialog?.parentElement;
    if (dialog && parent) {
      Array.from(parent.children).forEach(child => {
        if (child === dialog || !(child instanceof HTMLElement)) return;
        inertedSiblings.push({
          element: child,
          inert: child.getAttribute('inert'),
          ariaHidden: child.getAttribute('aria-hidden'),
        });
        child.setAttribute('inert', '');
        child.setAttribute('aria-hidden', 'true');
      });
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusables = focusableElements(dialog);
      if (focusables.length === 0) {
        event.preventDefault();
        initialFocusRef.current?.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    window.setTimeout(() => initialFocusRef.current?.focus(), 0);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      inertedSiblings.forEach(({ element, inert, ariaHidden }) => {
        if (inert === null) element.removeAttribute('inert');
        else element.setAttribute('inert', inert);
        if (ariaHidden === null) element.removeAttribute('aria-hidden');
        else element.setAttribute('aria-hidden', ariaHidden);
      });
      previous?.focus();
    };
  }, [initialFocusRef, onClose]);

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      data-testid={testId}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(15, 23, 42, 0.48)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      {children}
    </div>
  );
}
