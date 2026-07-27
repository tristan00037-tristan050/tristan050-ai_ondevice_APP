import { describe, expect, it, vi } from 'vitest';
import {
  readSetupBannerDismissed,
  SETUP_BANNER_DISMISSED_KEY,
  shouldShowSetupBanner,
  toSetupUiState,
  writeSetupBannerDismissed,
} from './setupBanner';

describe('setup banner state contract', () => {
  it('does not infer company setup completion from a missing signal', () => {
    const unavailable = toSetupUiState(undefined);
    expect(unavailable).toEqual({
      kind: 'unavailable',
      reason: 'canonical-signal-missing',
    });
    expect(shouldShowSetupBanner(unavailable, false)).toBe(true);
  });

  it.each([
    ['loading', false],
    ['incomplete', true],
    ['complete', false],
  ] as const)('maps canonical %s correctly', (status, expected) => {
    expect(shouldShowSetupBanner(toSetupUiState({ status }), false)).toBe(expected);
  });

  it('fails open for guidance when storage read/write is denied', () => {
    const denied = {
      getItem: vi.fn(() => { throw new DOMException('denied', 'SecurityError'); }),
      setItem: vi.fn(() => { throw new DOMException('denied', 'SecurityError'); }),
    };
    expect(readSetupBannerDismissed(denied)).toBe(false);
    expect(() => writeSetupBannerDismissed(denied)).not.toThrow();
  });

  it('stores only the session dismissal sentinel', () => {
    const storage = { setItem: vi.fn() };
    writeSetupBannerDismissed(storage);
    expect(storage.setItem).toHaveBeenCalledWith(SETUP_BANNER_DISMISSED_KEY, '1');
  });
});
