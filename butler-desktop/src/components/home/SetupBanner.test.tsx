import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SETUP_BANNER_DISMISSED_KEY } from '../../lib/setupBanner';
import { SetupBanner } from './SetupBanner';

describe('SetupBanner', () => {
  afterEach(() => vi.restoreAllMocks());

  beforeEach(() => {
    window.sessionStorage.clear();
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      callback(0);
      return 1;
    });
  });

  it('keeps resolving and complete states out of the DOM', () => {
    const { rerender } = render(
      <SetupBanner setup={{ kind: 'resolving' }} onStart={vi.fn()} />,
    );
    expect(screen.queryByTestId('setup-banner')).not.toBeInTheDocument();
    rerender(<SetupBanner setup={{ kind: 'complete' }} onStart={vi.fn()} />);
    expect(screen.queryByTestId('setup-banner')).not.toBeInTheDocument();
  });

  it('uses the preserved start handler and native button', () => {
    const onStart = vi.fn();
    render(
      <SetupBanner
        setup={{ kind: 'unavailable', reason: 'canonical-signal-missing' }}
        onStart={onStart}
      />,
    );
    const start = screen.getByRole('button', { name: /^시작하기$/ });
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalledOnce();
    expect(start.tagName).toBe('BUTTON');
  });

  it('dismisses for the tab session and moves focus to the next action', () => {
    render(
      <>
        <SetupBanner setup={{ kind: 'incomplete' }} onStart={vi.fn()} />
        <button data-home-card="true">첫 카드</button>
      </>,
    );
    const dismiss = screen.getByRole('button', { name: '시작하기 안내 닫기' });
    dismiss.focus();
    fireEvent.click(dismiss);
    expect(screen.queryByTestId('setup-banner')).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem(SETUP_BANNER_DISMISSED_KEY)).toBe('1');
    expect(screen.getByRole('button', { name: '첫 카드' })).toHaveFocus();
  });
});
